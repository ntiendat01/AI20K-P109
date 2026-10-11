import os
from dotenv import load_dotenv

# Load biến môi trường từ file .env (nếu có)
load_dotenv()

class MonitorSettings:
    @property
    def LANGSMITH_ENABLED(self) -> bool:
        return os.getenv("LANGSMITH_ENABLED", "false").lower() == "true"
    
    @property
    def LANGFUSE_ENABLED(self) -> bool:
        return os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"

    @property
    def LANGFUSE_SESSION_ID_PREFIX(self) -> str:
        return os.getenv("LANGFUSE_SESSION_ID_PREFIX", "procurement-")

    @property
    def MAX_REVISE_COUNT(self) -> int:
        return int(os.getenv("MAX_REVISE_COUNT", "3"))

    @property
    def MONITOR_ALERT_ENABLED(self) -> bool:
        return os.getenv("MONITOR_ALERT_ENABLED", "true").lower() == "true"

settings = MonitorSettings()
