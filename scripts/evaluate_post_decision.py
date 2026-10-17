"""Offline §11.8 benchmark. Run: python -m scripts.evaluate_post_decision --output PATH."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import tempfile
from decimal import Decimal
from pathlib import Path

from src.application.evaluation.engine import Evaluator
from src.application.evaluation.workflow import EvaluationWorkflow
from src.infrastructure.evaluation.store import EvaluationStore
from tests.fixtures.evaluation_cases import adapter, chunks, context, proposal


def measure(iterations: int = 40) -> dict[str, object]:
    """Measure targeted unsupported claims against hand-authored mutation oracles."""
    cases = []
    all_latency = []
    false_support = 0
    unsupported_trials = 0
    for case in ["valid", "wrong_number", "missing_source", "wrong_unit", "conflicting_source", "wrong_time_origin"]:
        latency = []
        statuses = set()
        for _ in range(iterations):
            p, c, a = proposal(), context(), adapter()
            target = "cl-A-cost"
            if case == "wrong_number":
                p.claims[0].predicate.value = Decimal("999")
            elif case == "missing_source":
                a.collection.records.pop("chunk-A-tco")
            elif case in {"wrong_unit", "conflicting_source"}:
                source = chunks()[0]
                if case == "wrong_unit":
                    source.facts[0].unit = source.facts[0].unit_text = "EUR"
                    source.text = "TCO: 12000 EUR."
                else:
                    source.chunk_id = "contradiction"
                    source.facts[0].value = Decimal("13000")
                    source.facts[0].value_text = "13000"
                    source.text = "TCO: 13000 USD."
                from src.infrastructure.evaluation.evidence import content_hash

                source.chunk_hash = content_hash(source.text)
                a.collection.replace(source)
            elif case == "wrong_time_origin":
                p.claims[2].predicate.time_origin = "payment_received"
                target = "cl-A-delivery"
            result = Evaluator(a, backoff_seconds=0).evaluate(p, c)
            latency.append(result.latency_ms)
            statuses.add(result.overall_status)
            if case != "valid":
                unsupported_trials += 1
                false_support += int(
                    any(e.claim_id == target and e.support_status == "supported" for e in result.evidence)
                )
        all_latency.extend(latency)
        cases.append(
            {
                "case": case,
                "trials": iterations,
                "statuses": sorted(statuses),
                "p50_ms": round(statistics.median(latency), 3),
                "p95_ms": round(statistics.quantiles(latency, n=20)[18], 3),
            }
        )

    class StalledRepair:
        calls = 0

        def repair(self, output, evaluation):
            self.calls += 1
            return output

    with tempfile.TemporaryDirectory() as directory:
        model = StalledRepair()
        workflow = EvaluationWorkflow(Evaluator(adapter()), EvaluationStore(Path(directory) / "repair.sqlite"), model)
        invalid = proposal()
        invalid.claims[0].predicate.value = Decimal("999")
        repair_result = workflow.submit(invalid, context())
    return {
        "dataset": "anonymous hand-computable fixtures; six inputs, repeated trials are not independent examples",
        "backend": "Offline evidence fake; production retrieval uses PostgreSQL with pgvector",
        "retrieval_k": 8,
        "cache": False,
        "concurrency": 1,
        "cases": cases,
        "total_trials": len(all_latency),
        "unsupported_claim_trials": unsupported_trials,
        "false_support_count": false_support,
        "false_support_rate": false_support / unsupported_trials,
        "p50_ms": round(statistics.median(all_latency), 3),
        "p95_ms": round(statistics.quantiles(all_latency, n=20)[18], 3),
        "stalled_repair_calls": model.calls,
        "stalled_repair_action": repair_result.required_actions[0].type,
        "baseline": "Previous evaluate node was pass-through; no comparable grounding metric. make eval is a no-op (no target).",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    logging.basicConfig(level=logging.INFO)
    logging.info(
        "Post-decision benchmark: trials=%s false_support=%s p95_ms=%s",
        result["total_trials"],
        result["false_support_count"],
        result["p95_ms"],
    )
    if result["false_support_count"] or result["stalled_repair_calls"] > 2:
        raise SystemExit("Acceptance benchmark failed")


if __name__ == "__main__":
    main()
