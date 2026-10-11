import logging
from monitor.config.settings import settings

logger = logging.getLogger(__name__)


class LangfuseAdapter:
    def is_enabled(self) -> bool:
        return settings.LANGFUSE_ENABLED

    def get_callbacks(self, session_id: str = None, user_id: str = None, tags: list = None) -> list:
        # Langfuse v2.x dùng langfuse.callback.CallbackHandler
        # Langfuse v3.x+ dùng langfuse.langchain.CallbackHandler
        CallbackHandler = None
        try:
            from langfuse.callback import CallbackHandler
        except ImportError:
            try:
                from langfuse.langchain import CallbackHandler
            except ImportError:
                pass

        if CallbackHandler is None:
            logger.warning(
                "LangfuseAdapter: Không tìm thấy CallbackHandler. "
                "Hãy chạy: pip install langfuse"
            )
            return []

        try:
            kwargs = {}
            if session_id:
                kwargs['session_id'] = f"{settings.LANGFUSE_SESSION_ID_PREFIX}{session_id}"
            if user_id:
                kwargs['user_id'] = user_id
            if tags:
                kwargs['tags'] = tags

            try:
                handler = CallbackHandler(**kwargs)
            except TypeError:
                # Fallback if specific version of CallbackHandler doesn't accept init kwargs
                handler = CallbackHandler()

            logger.info(f"LangfuseAdapter: Đã khởi tạo CallbackHandler thành công. (Session: {kwargs.get('session_id')})")
            return [handler]
        except Exception as e:
            logger.warning(f"LangfuseAdapter: Không thể khởi tạo CallbackHandler: {e}")
            return []
