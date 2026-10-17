"""Compose feature routers without placing endpoint implementations in a package initializer."""

from fastapi import APIRouter

from src.api.routes.procurement import router as procurement_router
from src.api.routes.settings import router as settings_router

router = APIRouter()
router.include_router(procurement_router)
router.include_router(settings_router)
