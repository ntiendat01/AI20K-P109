"""OCR engine adapter supporting RapidOCR (ONNXRuntime) and PaddleOCR."""

from __future__ import annotations

import logging
import os
import tempfile
import urllib.request
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

import pymupdf as fitz

from ocr.ocr_service.settings import OCRServiceSettings
from src.infrastructure.ocr.contracts import OCRLine, OCRPage

logger = logging.getLogger(__name__)

LATIN_ONNX_MODEL_URL = (
    "https://huggingface.co/breezedeus/cnocr-ppocr-latin_PP-OCRv3/resolve/main/latin_PP-OCRv3_rec_infer.onnx"
)


class OCREngine(Protocol):
    """Engine behavior consumed by the OCR HTTP layer."""

    def warm_up(self) -> None:
        """Load model assets before the service declares readiness."""

    def extract(self, document: bytes, suffix: str) -> list[OCRPage]:
        """Extract OCR pages from a validated document payload."""


def ensure_latin_rec_model(models_dir: str) -> str:
    """Ensure the Latin/Vietnamese ONNX recognition model is cached locally."""
    target_dir = Path(models_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "latin_PP-OCRv3_rec_infer.onnx"
    if not target_file.exists() or target_file.stat().st_size == 0:
        logger.info("Downloading Latin/Vietnamese OCR ONNX model from %s to %s", LATIN_ONNX_MODEL_URL, target_file)
        urllib.request.urlretrieve(LATIN_ONNX_MODEL_URL, str(target_file))
    return str(target_file)


class RapidOCREngine:
    """Lightweight ONNXRuntime-based OCR engine."""

    def __init__(self, settings: OCRServiceSettings):
        self._settings = settings
        self._client: Any = None

    def warm_up(self) -> None:
        self._get_client()

    def extract(self, document: bytes, suffix: str) -> list[OCRPage]:
        pages: list[OCRPage] = []
        is_pdf = (suffix and suffix.lower() == ".pdf") or document.startswith(b"%PDF-")

        if is_pdf:
            with fitz.open(stream=document, filetype="pdf") as doc:
                for index, page in enumerate(doc, start=1):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    img_bytes = pix.tobytes("png")
                    raw_lines = self._ocr_bytes(img_bytes)
                    lines = _extract_page_lines(raw_lines)
                    pages.append(
                        OCRPage(
                            page_number=index,
                            raw_text="\n".join(line.text for line in lines),
                            lines=lines,
                        )
                    )
        else:
            raw_lines = self._ocr_bytes(document)
            lines = _extract_page_lines(raw_lines)
            pages.append(
                OCRPage(
                    page_number=1,
                    raw_text="\n".join(line.text for line in lines),
                    lines=lines,
                )
            )

        return pages

    def _ocr_bytes(self, img_bytes: bytes) -> list[Any]:
        client = self._get_client()
        try:
            import cv2
            import numpy as np

            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return []
            result, _ = client(img)
            return result or []
        except Exception:
            # Fallback to tempfile if OpenCV decode fails
            handle, path = tempfile.mkstemp(suffix=".png")
            try:
                with os.fdopen(handle, "wb") as output:
                    output.write(img_bytes)
                result, _ = client(path)
                return result or []
            finally:
                Path(path).unlink(missing_ok=True)

    def _get_client(self) -> Any:
        if self._client is None:
            from rapidocr_onnxruntime import RapidOCR

            kwargs: dict[str, Any] = {}
            if self._settings.ocr_det_model_path:
                kwargs["det_model_path"] = self._settings.ocr_det_model_path

            dict_file = Path(__file__).parent / "models" / "latin_dict.txt"
            if self._settings.ocr_rec_keys_path:
                kwargs["rec_char_dict_path"] = self._settings.ocr_rec_keys_path
            elif dict_file.exists():
                kwargs["rec_char_dict_path"] = str(dict_file)

            if self._settings.ocr_rec_model_path:
                kwargs["rec_model_path"] = self._settings.ocr_rec_model_path
            elif self._settings.ocr_model_language == "vi":
                try:
                    kwargs["rec_model_path"] = ensure_latin_rec_model(self._settings.ocr_models_dir)
                except Exception as exc:
                    logger.warning("Could not download Latin ONNX model: %s. Using default RapidOCR model.", exc)

            self._client = RapidOCR(**kwargs)
        return self._client


class PaddleOCREngine:
    """PaddleOCR adapter preserved for backwards compatibility."""

    def __init__(self, settings: OCRServiceSettings):
        self._settings = settings
        self._client: object | None = None

    def warm_up(self) -> None:
        self._get_client()

    def extract(self, document: bytes, suffix: str) -> list[OCRPage]:
        path = self._write_temporary_document(document, suffix)
        try:
            result = self._get_client().ocr(path)
        finally:
            Path(path).unlink(missing_ok=True)
        return _to_pages(result)

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            module = import_module("paddleocr")
            paddle_ocr_class = getattr(module, "PaddleOCR")
            self._client = paddle_ocr_class(
                lang=self._settings.ocr_model_language,
                ocr_version=self._settings.ocr_model_version,
                use_doc_orientation_classify=self._settings.ocr_use_doc_orientation_classify,
                use_doc_unwarping=self._settings.ocr_use_doc_unwarping,
                use_textline_orientation=self._settings.ocr_use_textline_orientation,
                enable_mkldnn=False,
            )
        return self._client

    @staticmethod
    def _write_temporary_document(document: bytes, suffix: str) -> str:
        handle, path = tempfile.mkstemp(suffix=suffix or ".bin")
        try:
            with os.fdopen(handle, "wb") as output:
                output.write(document)
        except BaseException:
            Path(path).unlink(missing_ok=True)
            raise
        return path


def get_engine_class(settings: OCRServiceSettings) -> type[OCREngine]:
    if getattr(settings, "ocr_engine_type", "rapidocr").lower() == "paddleocr":
        return PaddleOCREngine
    return RapidOCREngine


def _to_pages(result: object) -> list[OCRPage]:
    if not isinstance(result, list):
        return []
    pages: list[OCRPage] = []
    for index, page in enumerate(result, start=1):
        lines = _extract_page_lines(page)
        pages.append(
            OCRPage(
                page_number=index,
                raw_text="\n".join(line.text for line in lines),
                lines=lines,
            )
        )
    return pages


def _extract_page_lines(page: object) -> list[OCRLine]:
    """Normalize RapidOCR [box, text, score], PaddleOCR [box, (text, score)], and dict result shapes."""
    if isinstance(page, dict):
        rec_texts = page.get("rec_texts", [])
        rec_scores = page.get("rec_scores", [])
        if isinstance(rec_texts, Iterable) and not isinstance(rec_texts, (str, bytes, dict)):
            lines: list[OCRLine] = []
            for index, text in enumerate(rec_texts):
                if isinstance(text, str) and text.strip():
                    score = (
                        rec_scores[index]
                        if isinstance(rec_scores, (list, tuple))
                        and index < len(rec_scores)
                        and isinstance(rec_scores[index], (int, float))
                        else None
                    )
                    lines.append(OCRLine(text=text.strip(), confidence=float(score) if score is not None else None))
            return lines
        return []

    if not isinstance(page, list):
        return []

    lines = []
    for line in page:
        if not isinstance(line, (list, tuple)):
            continue
        # RapidOCR format: [box, text, score]
        if len(line) >= 3 and isinstance(line[1], str) and isinstance(line[2], (int, float, str)):
            text = line[1].strip()
            if text:
                try:
                    score = float(line[2])
                except (ValueError, TypeError):
                    score = None
                lines.append(OCRLine(text=text, confidence=score))
            continue
        # PaddleOCR format: [box, (text, score)]
        if len(line) == 2:
            recognition = line[1]
            if isinstance(recognition, (list, tuple)) and recognition:
                text = recognition[0]
                if isinstance(text, str) and text.strip():
                    score = (
                        float(recognition[1])
                        if len(recognition) > 1 and isinstance(recognition[1], (int, float))
                        else None
                    )
                    lines.append(OCRLine(text=text.strip(), confidence=score))
    return lines
