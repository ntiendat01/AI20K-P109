"""Chroma ingestion and scoped Query/Get retrieval; similarity never verifies claims."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from pydantic import ValidationError

from src.models.evaluation import (
    Chunk,
    Claim,
    DecisionProposal,
    EvidenceArtifact,
    EvidenceSource,
    RetrievalTrace,
    RuntimeEvaluationContext,
    SourceScope,
)


class EvidenceUnavailableError(RuntimeError):
    """A transient corpus/index/service failure, distinct from a missing fact."""


class SourceIntegrityError(RuntimeError):
    """A returned record violated authorized scope or content integrity."""


class ChromaCollection(Protocol):
    def query(self, **kwargs: Any) -> dict[str, Any]: ...
    def get(self, **kwargs: Any) -> dict[str, Any]: ...
    def upsert(self, **kwargs: Any) -> Any: ...


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authorized(chunk: Chunk, scope: SourceScope, supplier_ids: list[str]) -> bool:
    return (
        chunk.tenant_id == scope.tenant_id
        and chunk.case_id == scope.case_id
        and scope.document_hashes.get(chunk.document_id) == chunk.document_hash
        and chunk.supplier_id in supplier_ids
        and chunk.source_kind in scope.source_kinds
        and content_hash(chunk.text) == chunk.chunk_hash
    )


class ChromaEvidenceAdapter:
    """Dependency injection accepts an actual Chroma Collection or an offline test double."""

    def __init__(self, collection: ChromaCollection, *, k: int = 8, ready: bool = True) -> None:
        if k < 1:
            raise ValueError("k must be positive")
        self.collection, self.k, self.ready = collection, k, ready

    def ingest(self, chunks: list[Chunk]) -> None:
        """Persist exact text and scalar Chroma metadata, preserving table relationships."""
        for chunk in chunks:
            if content_hash(chunk.text) != chunk.chunk_hash:
                raise SourceIntegrityError("Chunk content hash mismatch")
            if chunk.table_id and not (chunk.row_id and chunk.cell_locator):
                raise SourceIntegrityError("Table row/cell locators are required")
            if any(f.supplier_id != chunk.supplier_id for f in chunk.facts):
                raise SourceIntegrityError("Source fact supplier mismatch")
        if chunks:
            self.collection.upsert(
                ids=[c.chunk_id for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[
                    {
                        "tenant_id": c.tenant_id,
                        "case_id": c.case_id,
                        "supplier_id": c.supplier_id,
                        "document_id": c.document_id,
                        "document_hash": c.document_hash,
                        "source_kind": c.source_kind,
                        "chunk_hash": c.chunk_hash,
                        "record_json": c.model_dump_json(exclude={"text", "chunk_id"}),
                    }
                    for c in chunks
                ],
            )

    @staticmethod
    def where(scope: SourceScope, suppliers: list[str]) -> dict[str, Any]:
        if not scope.document_hashes or not suppliers or not scope.source_kinds:
            raise SourceIntegrityError("Empty authorized source scope")
        documents = [
            {"$and": [{"document_id": {"$eq": doc}}, {"document_hash": {"$eq": revision}}]}
            for doc, revision in scope.document_hashes.items()
        ]
        return {
            "$and": [
                {"tenant_id": {"$eq": scope.tenant_id}},
                {"case_id": {"$eq": scope.case_id}},
                {"supplier_id": {"$in": suppliers}},
                {"source_kind": {"$in": scope.source_kinds}},
                documents[0] if len(documents) == 1 else {"$or": documents},
            ]
        }

    def _get(self, ids: list[str], scope: SourceScope, suppliers: list[str]) -> list[Chunk]:
        if not ids:
            return []
        result = self.collection.get(
            ids=list(dict.fromkeys(ids)), where=self.where(scope, suppliers), include=["documents", "metadatas"]
        )
        chunks: list[Chunk] = []
        try:
            records = zip(result["ids"], result["documents"], result["metadatas"], strict=True)
            for chunk_id, text, metadata in records:
                chunk = Chunk.model_validate(
                    {**json.loads(metadata["record_json"]), "text": text, "chunk_id": chunk_id}
                )
                if chunk_id not in ids or not authorized(chunk, scope, suppliers):
                    raise SourceIntegrityError("Query/Get returned unauthorized or changed source")
                # Indexed access metadata and the serialized record must agree.
                for key in (
                    "tenant_id",
                    "case_id",
                    "supplier_id",
                    "document_id",
                    "document_hash",
                    "source_kind",
                    "chunk_hash",
                ):
                    if metadata.get(key) != getattr(chunk, key):
                        raise SourceIntegrityError("Indexed metadata mismatch")
                chunks.append(chunk)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise SourceIntegrityError("Malformed exact source record") from exc
        return chunks

    def retrieve(self, proposal: DecisionProposal, context: RuntimeEvaluationContext) -> list[EvidenceArtifact]:
        if not self.ready:
            raise EvidenceUnavailableError("Source index is not ready")
        try:
            return [self._claim(claim, context) for claim in proposal.claims]
        except (TimeoutError, ConnectionError, OSError) as exc:
            raise EvidenceUnavailableError("Chroma service unavailable") from exc
        except (SourceIntegrityError, EvidenceUnavailableError):
            raise
        except Exception as exc:
            raise EvidenceUnavailableError("Chroma index or query failed") from exc

    def _claim(self, claim: Claim, context: RuntimeEvaluationContext) -> EvidenceArtifact:
        ids: list[str] = []
        distances: list[float] = []
        # Each supplier is queried independently so a winner cannot crowd out alternatives.
        for supplier in claim.supplier_ids:
            query = " ".join(
                [claim.text, claim.predicate.metric, supplier, claim.predicate.model_dump_json(), *claim.source_hints]
            )
            result = self.collection.query(
                query_texts=[query],
                where=self.where(context.source_scope, [supplier]),
                n_results=self.k,
                include=["distances"],
            )
            try:
                ids.extend(result["ids"][0])
                distances.extend(result["distances"][0])
            except (KeyError, TypeError, IndexError) as exc:
                raise EvidenceUnavailableError("Invalid Chroma query response") from exc
        plans = [
            p
            for p in context.calculations
            if p.metric == claim.predicate.metric and p.supplier_id in claim.supplier_ids
        ]
        ids.extend(i for p in plans for i in p.operand_chunk_ids)
        chunks = self._get(ids, context.source_scope, claim.supplier_ids)
        expansion_ids = [
            i
            for c in chunks
            for i in ([c.parent_chunk_id, c.original_chunk_id] + c.context_chunk_ids)
            if i and i not in {x.chunk_id for x in chunks}
        ]
        expanded = self._get(expansion_ids, context.source_scope, claim.supplier_ids)
        chunks = list({c.chunk_id: c for c in chunks + expanded}.values())
        return EvidenceArtifact(
            evidence_id=f"ev:{context.recommendation_id}:{context.recommendation_version}:{claim.claim_id}",
            recommendation_id=context.recommendation_id,
            recommendation_version=context.recommendation_version,
            claim_id=claim.claim_id,
            evidence_kind="comparative" if claim.category == "comparison" else "derived" if plans else "direct_source",
            sources=[EvidenceSource(chunk=c, exact_excerpt=c.text, context_excerpt=c.text) for c in chunks],
            retrieval_trace=RetrievalTrace(
                query_id=f"query:{claim.claim_id}",
                candidate_chunk_ids=list(dict.fromkeys(ids)),
                distances=distances,
                expansion_count=int(bool(expansion_ids)),
            ),
        )
