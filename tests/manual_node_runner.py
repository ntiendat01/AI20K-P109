"""Run one procurement node at a time and persist state between runs.

Examples:
    python tests/manual_node_runner.py init --document path/to/quote.pdf
    python tests/manual_node_runner.py extract_ocr
    python tests/manual_node_runner.py extract_llm --extractor gemini
    python tests/manual_node_runner.py validate_extraction
    python tests/manual_node_runner.py normalize
    python tests/manual_node_runner.py decision_llm
    python tests/manual_node_runner.py show

Use ``--input`` with ``init`` to start from your own JSON state. By default,
state is stored in ``data/manual_node_test/state.json`` and every successful
node run also creates a snapshot under ``data/manual_node_test/history``.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.agents.nodes import (  # noqa: E402
    decision_llm,
    evaluate,
    extract_documents,
    generate_evidence,
    human_review_extraction,
    human_review_recommendation,
    normalize,
    process_feedback,
    validate_extraction,
)
from src.agents.state import ProcurementAgentState  # noqa: E402
from src.infrastructure.documents.pdf_extractor import PDFTextExtractor  # noqa: E402
from src.infrastructure.quotation.ai_extraction import (  # noqa: E402
    GeminiAPIExtractionClient,
    GroqAPIExtractionClient,
    QwenAPIExtractionClient,
)

DEFAULT_STATE_FILE = PROJECT_ROOT / "data" / "manual_node_test" / "state.json"
Node = Callable[[ProcurementAgentState], ProcurementAgentState]


class OfflineDecisionModel:
    """Small deterministic model stub for testing decision_llm without an API."""

    def invoke(self, input: object) -> dict[str, object]:
        messages = input if isinstance(input, list) else []
        last_message = messages[-1] if messages else {}
        content = last_message.get("content", "{}") if isinstance(last_message, Mapping) else "{}"
        payload = json.loads(content) if isinstance(content, str) else {}
        tco_results = payload.get("tco_results", []) if isinstance(payload, Mapping) else []
        ranked = []
        for result in tco_results if isinstance(tco_results, list) else []:
            if not isinstance(result, Mapping):
                continue
            supplier = result.get("supplier_id", result.get("supplier"))
            total = result.get("total_tco", result.get("total", 0))
            if isinstance(supplier, str) and isinstance(total, (int, float)) and not isinstance(total, bool):
                ranked.append({"supplier": supplier, "rationale": f"TCO {total}"})
        ranked.sort(key=lambda item: float(item["rationale"].split()[-1]))
        return {"ranked": ranked}


NODES: dict[str, Node] = {
    "extract_documents": extract_documents,
    "validate_extraction": validate_extraction,
    "human_review_extraction": human_review_extraction,
    "normalize": normalize,
    "decision_llm": decision_llm,
    "evaluate": evaluate,
    "generate_evidence": generate_evidence,
    "human_review_recommendation": human_review_recommendation,
    "process_feedback": process_feedback,
}

EXTRACTION_STEPS = ["extract_ocr", "extract_llm"]
PIPELINE = [*EXTRACTION_STEPS, *[name for name in NODES if name != "extract_documents"]]
INTERRUPT_NODES = {"human_review_extraction", "human_review_recommendation"}

SAMPLE_STATE: ProcurementAgentState = {
    "case_id": "MANUAL-TEST-001",
    "pr_data": {
        "target_uom": "cai",
        "target_currency": "VND",
        "quantity": 10,
        "budget": 5_000_000,
    },
    "documents": [],
    "raw_extractions": [
        {
            "document": "sample-supplier-a.pdf",
            "supplier": "Supplier A",
            "supplier_id": "Supplier A",
            "items": [
                {
                    "item_name": "Sample item",
                    "unit": "cai",
                    "currency": "VND",
                    "unit_price": 100_000,
                    "quantity": 10,
                    "surcharges": 20_000,
                    "vat_rate": 0.1,
                    "lead_time_days": 5,
                    "warranty_months": 12,
                }
            ],
            "confidence_score": 0.95,
            "field_confidence": {"supplier": 0.95, "unit_price": 0.95},
            "field_needs_confirmation": {},
            "needs_confirmation": False,
            "confirmed_by_human": False,
        },
        {
            "document": "sample-supplier-b.pdf",
            "supplier": "Supplier B",
            "supplier_id": "Supplier B",
            "items": [
                {
                    "item_name": "Sample item",
                    "unit": "cai",
                    "currency": "VND",
                    "unit_price": 110_000,
                    "quantity": 10,
                    "surcharges": 0,
                    "vat_rate": 0.1,
                    "lead_time_days": 3,
                    "warranty_months": 18,
                }
            ],
            "confidence_score": 0.95,
            "field_confidence": {"supplier": 0.95, "unit_price": 0.95},
            "field_needs_confirmation": {},
            "needs_confirmation": False,
            "confirmed_by_human": False,
        },
    ],
}


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return cast(dict[str, object], value)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _initialize(state_file: Path, input_file: Path | None, documents: list[Path]) -> None:
    if input_file is None and documents:
        initial_state: dict[str, object] = {
            "case_id": "MANUAL-EXTRACTION-TEST",
            "pr_data": {},
            "documents": [str(document.resolve()) for document in documents],
        }
    elif input_file is None:
        initial_state = cast(dict[str, object], SAMPLE_STATE)
    else:
        initial_state = _read_json(input_file)
        if documents:
            initial_state["documents"] = [str(document.resolve()) for document in documents]
    _write_json(state_file, initial_state)
    history_dir = state_file.parent / "history"
    if history_dir.exists():
        shutil.rmtree(history_dir)
    logger.info(f"Initialized: {state_file}")


def _load_state(state_file: Path) -> ProcurementAgentState:
    if not state_file.is_file():
        raise FileNotFoundError(f"State file not found: {state_file}. Run the 'init' command first.")
    return cast(ProcurementAgentState, _read_json(state_file))


def _snapshot(state_file: Path, node_name: str, state: ProcurementAgentState) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snapshot = state_file.parent / "history" / f"{timestamp}-{node_name}.json"
    _write_json(snapshot, state)
    return snapshot


def _extract_ocr(state: ProcurementAgentState) -> dict[str, object]:
    """Run the shared text-first OCR pipeline and retain serialized output."""
    client = PDFTextExtractor()
    results: list[dict[str, object]] = []
    for document in state.get("documents", []):
        if not Path(document).is_file():
            results.append({"document": document, "text": "", "error": "Document file not found"})
            continue
        try:
            text = client.extract_text(document)
            results.append({"document": document, "text": text, "error": None})
        except Exception as exc:
            results.append({"document": document, "text": "", "error": str(exc)})
    return {"ocr_results": results}


class StoredOCRClient:
    """Serve persisted OCR text so extract_documents only invokes the LLM."""

    def __init__(self, results: object) -> None:
        self.text_by_document: dict[str, str] = {}
        if not isinstance(results, list):
            return
        for result in results:
            if not isinstance(result, Mapping):
                continue
            document = result.get("document")
            text = result.get("text")
            if isinstance(document, str) and isinstance(text, str):
                self.text_by_document[document] = text

    def extract_text(self, document_path: str) -> str:
        if document_path not in self.text_by_document:
            raise ValueError(f"No persisted OCR result for {document_path}")
        return self.text_by_document[document_path]


def _extract_llm(state: ProcurementAgentState, extractor_name: str) -> ProcurementAgentState:
    """Run only structured LLM extraction using OCR text saved by extract_ocr."""
    state_data = cast(dict[str, object], state)
    if "ocr_results" not in state_data:
        raise ValueError("No ocr_results in state. Run extract_ocr first.")
    extractor_map = {
        "qwen": QwenAPIExtractionClient,
        "gemini": GeminiAPIExtractionClient,
        "groq": GroqAPIExtractionClient,
    }
    extractor_cls = extractor_map.get(extractor_name, GeminiAPIExtractionClient)

    return extract_documents(
        state,
        ocr_client=StoredOCRClient(state_data["ocr_results"]),
        extraction_client=extractor_cls(),
    )


def _run_interrupt_node(
    node_name: str,
    state: ProcurementAgentState,
    feedback: object,
) -> ProcurementAgentState:
    graph = StateGraph(ProcurementAgentState)
    graph.add_node(node_name, NODES[node_name])
    graph.set_entry_point(node_name)
    graph.add_edge(node_name, END)
    compiled = graph.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": f"manual-{datetime.now().timestamp()}"}}

    first_result = compiled.invoke(state, config)
    interruptions = first_result.get("__interrupt__", ())
    if interruptions:
        logger.info("Interrupt payload:")
        for interruption in interruptions:
            logger.info(json.dumps(interruption.value, ensure_ascii=False, indent=2, default=str))
        result = compiled.invoke(Command(resume=feedback), config)
    else:
        result = first_result
    return cast(ProcurementAgentState, result)


def _run_node(
    state_file: Path,
    node_name: str,
    feedback: object,
    offline: bool,
    extractor_name: str,
) -> None:
    state = _load_state(state_file)
    if node_name == "extract_ocr":
        update = _extract_ocr(state)
    elif node_name == "extract_llm":
        update = _extract_llm(state, extractor_name)
    elif node_name in INTERRUPT_NODES:
        result = _run_interrupt_node(node_name, state, feedback)
        update = {key: value for key, value in result.items() if key != "__interrupt__" and state.get(key) != value}
    elif node_name == "decision_llm" and offline:
        update = decision_llm(state, llm=OfflineDecisionModel())
    else:
        update = NODES[node_name](state)
    if not isinstance(update, Mapping):
        raise TypeError(f"Node {node_name} returned {type(update).__name__}, expected a mapping")

    merged_state = cast(ProcurementAgentState, {**state, **dict(update)})
    _write_json(state_file, merged_state)
    snapshot = _snapshot(state_file, node_name, merged_state)

    logger.info(json.dumps(update, ensure_ascii=False, indent=2, default=str))
    logger.info(f"\nState saved: {state_file}")
    logger.info(f"Snapshot: {snapshot}")
    if (
        node_name == "human_review_recommendation"
        and merged_state.get("human_feedback", {}).get("decision") != "revise"
    ):
        logger.info("Pipeline complete: recommendation approved")
        return
    if node_name not in PIPELINE:
        return
    current_index = PIPELINE.index(node_name)
    if current_index + 1 < len(PIPELINE):
        logger.info(f"Next node: {PIPELINE[current_index + 1]}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "show", *EXTRACTION_STEPS, *NODES])
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help=f"Persisted JSON state (default: {DEFAULT_STATE_FILE})",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Initial JSON state; only used by the init action",
    )
    parser.add_argument(
        "--document",
        type=Path,
        action="append",
        default=[],
        help="Document for init; repeat this option for multiple files",
    )
    parser.add_argument(
        "--feedback",
        default='{"decision": "approved"}',
        help="JSON response for a human-review node",
    )
    parser.add_argument(
        "--decision",
        choices=["approved", "revise"],
        help="Convenient human-review decision; overrides --feedback",
    )
    parser.add_argument("--note", help="Feedback note used with --decision")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use a deterministic local stub when running decision_llm",
    )
    parser.add_argument(
        "--extractor",
        choices=["gemini", "qwen", "groq"],
        default="gemini",
        help="LLM provider used by extract_llm (default: gemini)",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    state_file = args.state_file.resolve()
    try:
        feedback = json.loads(args.feedback)
        if args.decision:
            feedback = {"decision": args.decision}
            if args.note:
                feedback["note"] = args.note
        if args.action == "init":
            _initialize(state_file, args.input, args.document)
        elif args.action == "show":
            logger.info(json.dumps(_load_state(state_file), ensure_ascii=False, indent=2, default=str))
        else:
            _run_node(state_file, args.action, feedback, args.offline, args.extractor)
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.error("Error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
