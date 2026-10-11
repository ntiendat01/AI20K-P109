"""Anonymous, hand-computable acceptance inputs (12000 < 14500; 5 < 7; 24 > 12)."""

import json
from pathlib import Path

from src.models.evaluation import (
    Actor,
    Chunk,
    DecisionProposal,
    Fact,
    RuntimeEvaluationContext,
    SourceFact,
    SourceScope,
)
from src.services.evaluation.evidence import ChromaEvidenceAdapter, content_hash


def proposal() -> DecisionProposal:
    return DecisionProposal.model_validate_json((Path(__file__).parent / "evaluation/valid.json").read_text(encoding="utf-8"))


def context() -> RuntimeEvaluationContext:
    facts = [
        Fact(
            supplier_id=s, metric=m, value=v, unit=u, time_origin="order_confirmation" if m == "delivery_days" else None
        )
        for s, cost, days, warranty in [("A", "12000", "5", "12"), ("B", "14500", "7", "24")]
        for m, v, u in [
            ("tco", cost, "USD"),
            ("delivery_days", days, "calendar_day"),
            ("warranty_months", warranty, "month"),
        ]
    ]
    return RuntimeEvaluationContext(
        case_id="case-demo",
        recommendation_id="rec-demo",
        recommendation_version=1,
        candidate_ids=["A", "B"],
        facts=facts,
        mandatory_comparisons=["tco", "delivery_days", "warranty_months"],
        source_scope=SourceScope(
            tenant_id="tenant-demo", case_id="case-demo", document_hashes={"doc-A": "revision-A", "doc-B": "revision-B"}
        ),
        formula_allowlist=["sum_declared_tax_inclusive_components"],
        material_alternative_ids=["B"],
        optional_metrics=["quality"],
    )


def chunks() -> list[Chunk]:
    result = []
    for fact in context().facts:
        label, unit = {
            "tco": ("TCO", "USD"),
            "delivery_days": ("Delivery", "calendar days"),
            "warranty_months": ("Warranty", "months"),
        }[fact.metric]
        text = f"{label}: {fact.value} {unit}" + (" after order confirmation." if fact.time_origin else ".")
        result.append(
            Chunk(
                chunk_id=f"chunk-{fact.supplier_id}-{fact.metric}",
                text=text,
                chunk_hash=content_hash(text),
                tenant_id="tenant-demo",
                case_id="case-demo",
                document_id=f"doc-{fact.supplier_id}",
                document_hash=f"revision-{fact.supplier_id}",
                source_kind="quotation",
                supplier_id=fact.supplier_id,
                page=1,
                block_id=fact.metric,
                facts=[SourceFact(**fact.model_dump(), value_text=str(fact.value), metric_text=label, unit_text=unit)],
            )
        )
    return result


def actor() -> Actor:
    return Actor(actor_id="buyer-demo", tenant_id="tenant-demo", roles=["buyer"], case_ids=["case-demo"])


def matches(metadata, where):
    if "$and" in where:
        return all(matches(metadata, child) for child in where["$and"])
    if "$or" in where:
        return any(matches(metadata, child) for child in where["$or"])
    key, condition = next(iter(where.items()))
    return metadata.get(key) in condition["$in"] if "$in" in condition else metadata.get(key) == condition["$eq"]


class FakeChroma:
    """Query/Get-shaped fake, including real metadata-filter semantics and exact records."""

    def __init__(self):
        self.records = {}
        self.calls = []
        self.failures = 0
        self.ignore_filters = False

    def upsert(self, ids, documents, metadatas):
        for key, document, metadata in zip(ids, documents, metadatas, strict=True):
            self.records[key] = (document, metadata)

    def query(self, **kwargs):
        self.calls.append(("query", kwargs))
        if self.failures:
            self.failures -= 1
            raise TimeoutError("anonymous simulated outage")
        ids = [key for key, (_, meta) in self.records.items() if self.ignore_filters or matches(meta, kwargs["where"])][
            : kwargs["n_results"]
        ]
        return {"ids": [ids], "distances": [[0.001] * len(ids)]}

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        ids = [
            key
            for key in kwargs["ids"]
            if key in self.records and (self.ignore_filters or matches(self.records[key][1], kwargs["where"]))
        ]
        return {
            "ids": ids,
            "documents": [self.records[key][0] for key in ids],
            "metadatas": [self.records[key][1] for key in ids],
        }

    def replace(self, chunk):
        ChromaEvidenceAdapter(self).ingest([chunk])


def adapter() -> ChromaEvidenceAdapter:
    collection = FakeChroma()
    result = ChromaEvidenceAdapter(collection)
    result.ingest(chunks())
    return result


def oracles():
    return json.loads((Path(__file__).parent / "evaluation/oracles.json").read_text())
