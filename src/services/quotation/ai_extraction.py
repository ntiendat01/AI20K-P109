from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class OCRClient(Protocol):
    """Contract for converting a local document into OCR output."""

    def extract_text(self, document_path: str) -> str:
        """Return serialized OCR content for one document."""


class ExtractionClient(Protocol):
    """Contract for turning OCR content into quote line dictionaries."""

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        """Return structured quote lines for one document."""


class _PaddleSDKClient(Protocol):
    def ocr(self, *, file_path: str, model: object) -> object: ...

    def close(self) -> None: ...


class _PaddleModel(Protocol):
    PP_OCRV5: object


class PaddleOCRHostedClient:
    """Local PaddleOCR adapter since hosted API is down."""

    def extract_text(self, document_path: str) -> str:
        """Run OCR locally and return serialized text."""
        doc_name = Path(document_path).name
        logger.info("[OCR] Bắt đầu quét OCR tài liệu: %s (%s)", doc_name, document_path)

        module = import_module("paddleocr")
        paddle_ocr_class = getattr(module, "PaddleOCR")

        # Initialize local OCR engine (will download models if first time)
        client = paddle_ocr_class(lang="vi", ocr_version="PP-OCRv3", enable_mkldnn=False)
        result = client.ocr(document_path)

        extracted_pages = []
        total_lines = 0
        if isinstance(result, list):
            for idx, page in enumerate(result, 1):
                if page is None:
                    continue
                page_texts = _extract_page_texts(page)
                total_lines += len(page_texts)
                logger.debug("[OCR] Trang %d: nhận diện được %d dòng text", idx, len(page_texts))
                extracted_pages.append({"raw_text": "\n".join(page_texts)})

        total_chars = sum(len(p.get("raw_text", "")) for p in extracted_pages)
        logger.info(
            "[OCR] Hoàn tất: %s | Trang: %d | Dòng: %d | Ký tự: %d",
            doc_name,
            len(extracted_pages),
            total_lines,
            total_chars,
        )

        payload = {"pages": extracted_pages}
        return json.dumps(payload, ensure_ascii=False)


class QwenAPIExtractionClient:
    """OpenAI-compatible client for structured extraction with Qwen3-8B."""

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        """Ask Qwen for quote lines and validate the response envelope."""
        settings = get_settings()
        if not settings.qwen_base_url:
            raise RuntimeError("QWEN_BASE_URL is not configured")

        doc_name = Path(document_path).name
        logger.info("[LLM_EXTRACT:QWEN] Gửi request: model=%s, file=%s", settings.qwen_model_name, doc_name)

        headers = {"Content-Type": "application/json"}
        if settings.qwen_api_key:
            headers["Authorization"] = f"Bearer {settings.qwen_api_key}"

        payload = {
            "model": settings.qwen_model_name,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": settings.extraction_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"document": document_path, "ocr_result": ocr_text},
                        ensure_ascii=False,
                    ),
                },
            ],
        }

        try:
            response = httpx.post(
                f"{settings.qwen_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=settings.qwen_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            logger.error("[LLM_EXTRACT:QWEN] Timeout sau %s giây: %s", settings.qwen_timeout_seconds, exc)
            raise TimeoutError(f"Qwen extraction timed out after {settings.qwen_timeout_seconds:g} seconds") from exc

        response.raise_for_status()
        resp_json = cast(dict[str, object], response.json())
        usage = resp_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        logger.info(
            "[LLM_TOKEN_USAGE:QWEN] Input: %s, Output: %s, Total: %s", prompt_tokens, completion_tokens, total_tokens
        )

        items = _parse_qwen_response(resp_json)
        logger.info("[LLM_EXTRACT:QWEN] Trích xuất thành công %d items từ %s", len(items), doc_name)
        return items


class GeminiAPIExtractionClient:
    """Gemini API client for structured extraction."""

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        doc_name = Path(document_path).name
        logger.info("[LLM_EXTRACT:GEMINI] Gửi request: model=%s, file=%s", settings.gemini_model_name, doc_name)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model_name}:generateContent?key={settings.gemini_api_key}"

        prompt = f"{settings.extraction_prompt}\n\nDocument path: {document_path}\n\nOCR Result:\n{ocr_text}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }

        try:
            response = httpx.post(url, json=payload, timeout=60.0)
            response.raise_for_status()

            data = response.json()
            usage = data.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount", 0)
            completion_tokens = usage.get("candidatesTokenCount", 0)
            total_tokens = usage.get("totalTokenCount", prompt_tokens + completion_tokens)
            logger.info(
                "[LLM_TOKEN_USAGE:GEMINI] Input: %s, Output: %s, Total: %s",
                prompt_tokens,
                completion_tokens,
                total_tokens,
            )

            content = data["candidates"][0]["content"]["parts"][0]["text"]
            logger.debug("[LLM_EXTRACT:GEMINI] Response received: content_length=%d", len(content))

            decoded = json.loads(content)
            items = decoded.get("items")
            if not isinstance(items, list):
                raise ValueError("Gemini content does not contain an items array")
            parsed_items = [cast(dict[str, object], item) for item in items if isinstance(item, dict)]
            logger.info("[LLM_EXTRACT:GEMINI] Trích xuất thành công %d items từ %s", len(parsed_items), doc_name)
            return parsed_items

        except httpx.TimeoutException as exc:
            logger.error("[LLM_EXTRACT:GEMINI] Timeout: %s", exc)
            raise TimeoutError("Gemini extraction timed out") from exc
        except Exception as exc:
            logger.error("[LLM_EXTRACT:GEMINI] Lỗi: %s", exc)
            raise ValueError(f"Gemini extraction failed: {exc}") from exc


class GroqAPIExtractionClient:
    """OpenAI-compatible client for structured extraction with Groq / Custom LLM."""

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        settings = get_settings()
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        doc_name = Path(document_path).name
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {settings.groq_api_key}"}
        base_url = settings.groq_base_url.rstrip("/")

        # Mở rộng context cho gpt-oss-20b (tổng giới hạn 8000 in/out tokens).
        # Dành 3500 token cho output JSON, cho phép input đạt tới 4500 token.
        ocr_text_fitted = _fit_context_window(
            ocr_text, settings.extraction_prompt, document_path, max_input_tokens=4500
        )
        logger.info(
            "[LLM_EXTRACT:GROQ] Gửi request: model=%s, file=%s, text_len=%d",
            settings.groq_model_name,
            doc_name,
            len(ocr_text_fitted),
        )

        payload = {
            "model": settings.groq_model_name,
            "temperature": 0,
            "max_tokens": 3500,
            "messages": [
                {"role": "system", "content": settings.extraction_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"document": document_path, "ocr_result": ocr_text_fitted},
                        ensure_ascii=False,
                    ),
                },
            ],
        }

        try:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0,
            )
        except httpx.TimeoutException as exc:
            logger.error("[LLM_EXTRACT:GROQ] Timeout sau 60s: %s", exc)
            raise TimeoutError("Groq/Custom LLM extraction timed out") from exc

        response.raise_for_status()
        resp_json = cast(dict[str, object], response.json())
        usage = resp_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        logger.info(
            "[LLM_TOKEN_USAGE:GROQ] Input: %s, Output: %s, Total: %s", prompt_tokens, completion_tokens, total_tokens
        )

        items = _parse_qwen_response(resp_json)
        logger.info("[LLM_EXTRACT:GROQ] Trích xuất thành công %d items từ %s", len(items), doc_name)
        return items


def _fit_context_window(
    ocr_text: str,
    system_prompt: str,
    doc_path: str,
    max_input_tokens: int = 4500,
) -> str:
    """Đảm bảo tổng input token (prompt + OCR) nằm trong ngưỡng an toàn (~4500 tokens),
    dành 3500 token còn lại cho output JSON để không vượt 8000 token limit của model.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        base_tokens = len(enc.encode(system_prompt)) + len(enc.encode(doc_path)) + 50
        allowed_ocr_tokens = max(500, max_input_tokens - base_tokens)
        ocr_tokens = enc.encode(ocr_text)
        if len(ocr_tokens) <= allowed_ocr_tokens:
            return ocr_text
        return enc.decode(ocr_tokens[:allowed_ocr_tokens]) + "\n...[TRUNCATED TO FIT 8K CONTEXT]..."
    except Exception:
        # Fallback ước tính theo ký tự (~3.5 ký tự / token)
        max_chars = max_input_tokens * 3
        if len(ocr_text) <= max_chars:
            return ocr_text
        return ocr_text[:max_chars] + "\n...[TRUNCATED TO FIT 8K CONTEXT]..."


def _serialize_result(result: object) -> str:
    pages = getattr(result, "pages", [])
    serialized_pages: list[dict[str, object]] = []
    if isinstance(pages, list):
        for page in pages:
            serialized_pages.append(
                {
                    "pruned_result": getattr(page, "pruned_result", None),
                    "raw": getattr(page, "raw", {}),
                }
            )
    payload = {
        "pages": serialized_pages,
        "data_info": getattr(result, "data_info", {}),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _extract_page_texts(page: object) -> list[str]:
    """Extract recognized lines from PaddleOCR v3 or legacy page output."""
    if isinstance(page, dict):
        rec_texts = page.get("rec_texts", [])
        if isinstance(rec_texts, Iterable) and not isinstance(rec_texts, (str, bytes, dict)):
            return [text for text in rec_texts if isinstance(text, str)]
        return []

    if not isinstance(page, list):
        return []

    texts: list[str] = []
    for line in page:
        if not isinstance(line, (list, tuple)) or len(line) != 2:
            continue
        recognition = line[1]
        if isinstance(recognition, (list, tuple)) and recognition:
            text = recognition[0]
            if isinstance(text, str):
                texts.append(text)
    return texts


def _parse_qwen_response(response: dict[str, object]) -> list[dict[str, object]]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Qwen response does not contain choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("Qwen choice has an invalid shape")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("Qwen response does not contain a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("Qwen message content is not text")

    logger.debug("Extraction LLM response received: content_length=%d", len(content))

    decoded = json.loads(_strip_json_fence(content))
    if not isinstance(decoded, dict):
        raise ValueError("Qwen content must be a JSON object")
    items = decoded.get("items")
    if not isinstance(items, list):
        raise ValueError("Qwen content does not contain an items array")
    return [cast(dict[str, object], item) for item in items if isinstance(item, dict)]


def _strip_json_fence(content: str) -> str:
    import re

    # Extract JSON object or array using regex
    match = re.search(r"(\{.*\}|\[.*\])", content, re.DOTALL)
    if match:
        return match.group(1)

    # Fallback to original stripping
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])
    return stripped


class ConfiguredExtraction:
    """Default ExtractionClient implementation using configured LLM."""

    def extract_items(self, ocr_text: str, document_path: str) -> list[dict[str, object]]:
        from src.services.llm import get_llm

        settings = get_settings()
        response = get_llm().invoke(
            [
                {"role": "system", "content": settings.extraction_prompt},
                {
                    "role": "user",
                    "content": json.dumps({"document": document_path, "ocr_result": ocr_text}, ensure_ascii=False),
                },
            ]
        )
        response_metadata = getattr(response, "response_metadata", {}) or {}
        usage = response_metadata.get("token_usage", {}) or {} if isinstance(response_metadata, dict) else {}
        if not usage and hasattr(response, "usage_metadata") and isinstance(response.usage_metadata, dict):
            usage = {
                "prompt_tokens": response.usage_metadata.get("input_tokens"),
                "completion_tokens": response.usage_metadata.get("output_tokens"),
                "total_tokens": response.usage_metadata.get("total_tokens"),
            }
        prompt_tokens = usage.get("prompt_tokens") or "N/A"
        completion_tokens = usage.get("completion_tokens") or "N/A"
        total_tokens = usage.get("total_tokens") or "N/A"
        logger.info(
            "Document extraction LLM tokens: prompt=%s completion=%s total=%s document=%s",
            prompt_tokens,
            completion_tokens,
            total_tokens,
            Path(document_path).name,
        )
        parsed = json.loads(_strip_json_fence(getattr(response, "content", "")))
        return parsed.get("items", []) if isinstance(parsed, dict) else []
