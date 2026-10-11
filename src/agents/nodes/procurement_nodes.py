from src.agents.state import ProcurementAgentState


# Phase 1: Extraction & Data Preparation
def extract_documents(state: ProcurementAgentState) -> dict:
    return {"normalized_quotes": [{"supplier": "Supplier A", "price": 1000}]}


def validate_extraction(state: ProcurementAgentState) -> dict:
    return {}


def human_review_extraction(state: ProcurementAgentState) -> dict:
    return {}


def normalize(state: ProcurementAgentState) -> dict:
    return {}


# Phase 2: Decision Making & Evaluation
def decision_llm(state: ProcurementAgentState) -> dict:
    return {"recommendation": {"selected_supplier": "Supplier A"}}


def evaluate(state: ProcurementAgentState) -> dict:
    return {}


def generate_evidence(state: ProcurementAgentState) -> dict:
    return {}


# Phase 3: Final Review & Feedback Loop
def human_review_recommendation(state: ProcurementAgentState) -> dict:
    return {}


def process_feedback(state: ProcurementAgentState) -> dict:
    count = state.get("revise_count", 0) + 1
    return {"revise_count": count}
