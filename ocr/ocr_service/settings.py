"""Settings owned by the isolated OCR service."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OCRServiceSettings(BaseSettings):
    """Runtime limits and credentials for the OCR boundary."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ocr_service_token: str = Field(default="", repr=False)
    ocr_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    ocr_max_pages: int = Field(default=100, gt=0)
    ocr_engine_type: str = "rapidocr"
    ocr_model_version: str = "PP-OCRv3"
    ocr_model_language: str = "vi"
    ocr_models_dir: str = "/opt/ocr-models"
    ocr_det_model_path: str = ""
    ocr_rec_model_path: str = ""
    ocr_rec_keys_path: str = ""
    ocr_use_doc_orientation_classify: bool = False
    ocr_use_doc_unwarping: bool = False
    ocr_use_textline_orientation: bool = False
