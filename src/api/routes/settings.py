"""API endpoints for reading and updating dynamic system settings."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.dependencies import get_current_user
from src.domain.settings import SystemSettings
from src.infrastructure.auth import DemoUser
from src.infrastructure.repositories.system_settings import (
    get_dynamic_settings,
    update_dynamic_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SystemSettings)
def read_settings(user: DemoUser = Depends(get_current_user)) -> SystemSettings:
    """Return the current dynamic system settings."""
    return get_dynamic_settings()


@router.put("", response_model=SystemSettings)
def save_settings(
    payload: dict[str, Any],
    user: DemoUser = Depends(get_current_user),
) -> SystemSettings:
    """Update dynamic system settings with role-based field restrictions."""
    current = get_dynamic_settings().model_dump()

    # Define fields allowed for each role
    procurement_allowed_fields = {
        "confidence_threshold",
        "high_confidence_threshold",
        "default_currency",
        "default_vat_rate",
        "auto_highlight_bbox",
        "auto_scroll_pdf",
        "auto_match_threshold",
        "suggest_threshold",
        "min_name_score",
        "synonyms",
    }

    if user.role == "procurement":
        # Buyer can only update operational fields
        for field, value in payload.items():
            if field in procurement_allowed_fields:
                current[field] = value
    elif user.role == "manager":
        # Manager has full authority to update all fields
        for field, value in payload.items():
            if field in current:
                current[field] = value
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vai trò không có quyền cập nhật cấu hình.",
        )

    updated_settings = SystemSettings.model_validate(current)
    saved = update_dynamic_settings(updated_settings)
    logger.info("System settings updated by user=%s (role=%s)", user.id, user.role)
    return saved
