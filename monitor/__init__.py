from monitor.core.facade import MonitorFacade

# Singleton instance
_facade = MonitorFacade()

def get_tracing_callbacks(session_id: str = None, user_id: str = None, tags: list = None):
    """Lấy danh sách các LangChain callbacks cho monitor."""
    return _facade.get_tracing_callbacks(session_id=session_id, user_id=user_id, tags=tags)

def log_system_resource(action: str, metadata: dict = None):
    """Ghi nhận tài nguyên hệ thống (CPU/RAM)."""
    _facade.log_system_resource(action, metadata)
