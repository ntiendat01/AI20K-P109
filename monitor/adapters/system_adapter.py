import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class SystemAdapter:
    def log_usage(self, action: str, metadata: dict = None):
        """
        Ghi nhận thông số CPU/RAM và in ra chuẩn JSON.
        """
        metadata = metadata or {}
        system_stats = {}
        
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            system_stats = {
                "cpu_percent": cpu_percent,
                "ram_percent": mem.percent,
                "ram_used_mb": round(mem.used / (1024 * 1024), 2)
            }
        except ImportError:
            # Fallback nếu không có psutil
            system_stats = {
                "error": "psutil is not installed",
                "cpu_percent": None,
                "ram_percent": None
            }
            
        log_entry = {
            "action": action,
            "phase": metadata.get("phase"),          # "extraction" | "decision" | "review"
            "node": metadata.get("node_name"),
            "thread_id": metadata.get("thread_id"),
            "system_stats": system_stats,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "metadata": metadata
        }
        
        logger.info(f"System Resource Log: {json.dumps(log_entry, ensure_ascii=False)}")
