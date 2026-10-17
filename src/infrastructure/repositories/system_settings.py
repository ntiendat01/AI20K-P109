"""Persistence repository and dynamic injection service for system settings."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock

from src.core.config import get_settings as get_core_settings
from src.domain.settings import SystemSettings
from src.infrastructure.persistence.postgres import PostgresRecordStore

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS_RECORD_ID = "default"
SETTINGS_NAMESPACE = "system_settings"


class SystemSettingsRepository:
    """Read and write dynamic system settings from PostgreSQL or fallback JSON file."""

    def __init__(self, database_url: str | None = None, fallback_path: Path | None = None) -> None:
        self.fallback_path = fallback_path or Path("data/system_settings.json")
        self.database_url = database_url
        self.store: PostgresRecordStore | None = None
        self._lock = Lock()
        self._cached: SystemSettings | None = None

        if self.database_url:
            try:
                self.store = PostgresRecordStore(self.database_url)
            except Exception as e:
                logger.warning("Could not initialize PostgresRecordStore for settings: %s. Using fallback JSON file.", e)
                self.store = None

    def get(self) -> SystemSettings:
        with self._lock:
            if self._cached is not None:
                return self._cached

            # 1. Try PostgreSQL store
            if self.store is not None:
                try:
                    records = self.store.load(SETTINGS_NAMESPACE)
                    for rec in records:
                        if rec.get("id") == DEFAULT_SETTINGS_RECORD_ID:
                            self._cached = SystemSettings.model_validate(rec.get("settings", {}))
                            return self._cached
                except Exception as e:
                    logger.warning("Failed to load settings from PostgresRecordStore: %s. Falling back to local file.", e)

            # 2. Try JSON file fallback
            if self.fallback_path.exists():
                try:
                    content = self.fallback_path.read_text(encoding="utf-8")
                    data = json.loads(content)
                    self._cached = SystemSettings.model_validate(data)
                    return self._cached
                except Exception as e:
                    logger.warning("Failed to parse settings from fallback file: %s", e)

            # 3. Default instance
            self._cached = SystemSettings()
            return self._cached

    def update(self, new_settings: SystemSettings) -> SystemSettings:
        with self._lock:
            payload = {
                "id": DEFAULT_SETTINGS_RECORD_ID,
                "settings": new_settings.model_dump(mode="json"),
            }

            # 1. Save to PostgreSQL if available
            if self.store is not None:
                try:
                    self.store.replace(SETTINGS_NAMESPACE, [payload])
                except Exception as e:
                    logger.warning("Failed to save settings to PostgresRecordStore: %s", e)

            # 2. Save to JSON fallback
            try:
                self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
                self.fallback_path.write_text(
                    json.dumps(new_settings.model_dump(mode="json"), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning("Failed to save settings to fallback file: %s", e)

            self._cached = new_settings
            logger.info("Dynamic system settings successfully updated.")
            return self._cached


_repository_instance: SystemSettingsRepository | None = None


def get_system_settings_repository() -> SystemSettingsRepository:
    """Return the singleton instance of SystemSettingsRepository."""
    global _repository_instance
    if _repository_instance is None:
        core_settings = get_core_settings()
        db_url = core_settings.database_url if core_settings.persistence_backend == "postgresql" else None
        _repository_instance = SystemSettingsRepository(database_url=db_url)
    return _repository_instance


def get_dynamic_settings() -> SystemSettings:
    """Convenient shortcut to fetch the current active dynamic system settings."""
    return get_system_settings_repository().get()


def update_dynamic_settings(new_settings: SystemSettings) -> SystemSettings:
    """Convenient shortcut to update active dynamic system settings."""
    return get_system_settings_repository().update(new_settings)
