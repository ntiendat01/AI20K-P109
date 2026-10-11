import os
import logging
from monitor.config.settings import settings

logger = logging.getLogger(__name__)

class LangSmithAdapter:
    def is_enabled(self) -> bool:
        return settings.LANGSMITH_ENABLED
    
    def get_callbacks(self) -> list:
        try:
            from langchain_core.tracers import LangChainTracer
            # Ensure the required environment variable for LangSmith is set
            if "LANGCHAIN_TRACING_V2" not in os.environ:
                os.environ["LANGCHAIN_TRACING_V2"] = "true"
            return [LangChainTracer()]
        except ImportError:
            logger.warning("LangSmithAdapter: langchain_core not found. Please install it to use LangSmith.")
            return []
