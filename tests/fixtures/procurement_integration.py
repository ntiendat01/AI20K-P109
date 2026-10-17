"""Anonymous decision provider for integration tests."""

import json


class ConfirmedDecisionModel:
    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        inputs = json.loads(messages[-1]["content"])
        candidates = sorted(
            inputs["allowed_supplier_ids"],
            key=lambda supplier_id: float(
                next(result["total_tco"] for result in inputs["tco_results"] if result["supplier_id"] == supplier_id)
            ),
        )
        preferred, alternative = candidates[0], candidates[1]
        return json.dumps(
            {
                "status": "proposed",
                "preferred_supplier_id": preferred,
                "ranked_supplier_ids": candidates[: inputs["top_n"]],
                "rationale": "Ưu tiên chi phí và thời gian giao; đối chiếu đánh đổi bảo hành.",
                "tradeoffs": [
                    {
                        "preferred_supplier_id": preferred,
                        "alternative_supplier_id": alternative,
                        "description": "Nhà cung cấp thay thế có điều khoản bảo hành khác cần cân nhắc.",
                    }
                ],
                "input_artifact_ids": inputs["input_artifact_ids"],
            },
            ensure_ascii=False,
        )


def integration_service(path):
    """Real local evidence/store/graph dependencies; only the model is a fixture."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    from src.application.evaluation.engine import Evaluator
    from src.infrastructure.evaluation.evidence import ChromaEvidenceAdapter
    from src.infrastructure.evaluation.store import EvaluationStore
    from src.application.evaluation.workflow import EvaluationWorkflow
    from src.application.procurement.workflow import LocalLexicalEmbeddings, ProcurementWorkflow

    client = chromadb.PersistentClient(path=str(path / "chroma"), settings=ChromaSettings(anonymized_telemetry=False))
    collection = client.get_or_create_collection("integration", embedding_function=LocalLexicalEmbeddings())
    evaluation = EvaluationWorkflow(
        Evaluator(ChromaEvidenceAdapter(collection)), EvaluationStore(path / "review.sqlite")
    )
    model = ConfirmedDecisionModel()
    return ProcurementWorkflow(path / "workflow.sqlite", evaluation, tenant_id="test", decision_model=model)
