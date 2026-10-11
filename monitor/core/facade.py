from typing import List, Any
import logging
from monitor.adapters.langsmith_adapter import LangSmithAdapter
from monitor.adapters.langfuse_adapter import LangfuseAdapter
from monitor.adapters.system_adapter import SystemAdapter

logger = logging.getLogger(__name__)

class MonitorFacade:
    def __init__(self):
        self.langsmith = LangSmithAdapter()
        self.langfuse = LangfuseAdapter()
        self.system = SystemAdapter()

    def get_tracing_callbacks(self, session_id: str = None, user_id: str = None, tags: list = None) -> List[Any]:
        """
        Trả về danh sách gộp các callback từ cả LangSmith và Langfuse.
        Hỗ trợ dual-tracking (gửi telemetry đến cả 2 nền tảng cùng lúc).
        """
        callbacks = []
        if self.langsmith.is_enabled():
            callbacks.extend(self.langsmith.get_callbacks())
        if self.langfuse.is_enabled():
            callbacks.extend(self.langfuse.get_callbacks(session_id=session_id, user_id=user_id, tags=tags))
        return callbacks

    def log_system_resource(self, action: str, metadata: dict = None):
        """
        Ghi nhận thông số CPU/RAM và metadata tại thời điểm gọi.
        """
        self.system.log_usage(action, metadata)

    def log_hitl_interrupt(self, checkpoint_name: str, thread_id: str, metadata: dict):
        """Tag sự kiện HITL Interrupt"""
        logger.info(f"HITL Interrupt [{checkpoint_name}] - Thread: {thread_id} - Metadata: {metadata}")
        self.log_system_resource("hitl_interrupt", {"checkpoint": checkpoint_name, "thread_id": thread_id, **(metadata or {})})

    def log_revision_loop(self, revise_count: int, thread_id: str, feedback_note: str):
        """Log revision loop + alert nếu >= 3"""
        logger.warning(f"Revision Loop - Thread: {thread_id} - Count: {revise_count} - Note: {feedback_note}")
        if revise_count >= 3:
            logger.error(f"ALERT: Revision count exceeded threshold (>= 3) for Thread: {thread_id}")
        self.log_system_resource("revision_loop", {"revise_count": revise_count, "thread_id": thread_id})

    def log_early_exit(self, node_name: str, reason: str, thread_id: str):
        """Tag early-exit từ check_data_ready hoặc evaluate_sufficiency"""
        logger.warning(f"Early Exit at [{node_name}] - Reason: {reason} - Thread: {thread_id}")
        self.log_system_resource("early_exit", {"node_name": node_name, "reason": reason, "thread_id": thread_id})

    def log_llm_node(self, node_name: str, tokens: dict, latency_ms: float, thread_id: str):
        """Log LLM-specific metrics (token + latency)"""
        logger.info(f"LLM Node [{node_name}] - Thread: {thread_id} - Latency: {latency_ms}ms - Tokens: {tokens}")
        self.log_system_resource("llm_metrics", {"node_name": node_name, "latency_ms": latency_ms, "tokens": tokens, "thread_id": thread_id})
