import time
import logging

import monitor
from src.agents.graph import agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Khởi động Mock Simulator cho Procurement AI Agent...")
    
    thread_id = "THREAD-20260930-01"
    
    # Lấy callbacks với session_id & tags để đẩy telemetry trực tiếp lên Langfuse & LangSmith
    callbacks = monitor.get_tracing_callbacks(
        session_id=thread_id,
        user_id="buyer_demo_01",
        tags=["procurement", "hitl-simulation"]
    )
    
    config = {
        "callbacks": callbacks,
        "configurable": {"thread_id": thread_id}
    }
    
    # 1. Phase 1: Execution in LangGraph
    logger.info("--- PHASE 1: Extraction & Data Preparation ---")
    monitor.log_system_resource("start_phase_1", {"phase": "extraction", "thread_id": thread_id})
    
    initial_state = {
        "metadata": {"confidence_low": False},
        "revise_count": 0
    }
    
    # Kích hoạt LangGraph Agent thực sự cùng với Callback Handler
    try:
        state_res = agent.invoke(initial_state, config=config)
        logger.info(f"LangGraph State sau khi chạy: {state_res}")
    except Exception as e:
        logger.warning(f"LangGraph interrupt hoặc thông báo: {e}")
    
    monitor._facade.log_llm_node("extract_documents", {"prompt_tokens": 120, "completion_tokens": 45}, 150.0, thread_id)
    monitor._facade.log_hitl_interrupt("human_review_extraction", thread_id, {"reason": "confidence_low"})
    
    time.sleep(1)
    
    # 2. Phase 2 & 3: Decision & Revision Loop Simulation
    logger.info("--- PHASE 2 & 3: Decision & Revision Loop ---")
    monitor.log_system_resource("start_phase_2", {"phase": "decision", "thread_id": thread_id})
    
    for revise_count in range(1, 4):
        monitor._facade.log_revision_loop(revise_count, thread_id, "Need better pricing options")
        monitor._facade.log_llm_node("decision_llm", {"prompt_tokens": 600, "completion_tokens": 150}, 500.0, thread_id)
        monitor._facade.log_hitl_interrupt("human_review_recommendation", thread_id, {"reason": "yield_to_buyer"})
        time.sleep(1)

    logger.info("Simulator hoàn tất thành công! Bạn có thể lên LangSmith & Langfuse Dashboard để review dữ liệu.")

if __name__ == "__main__":
    main()
