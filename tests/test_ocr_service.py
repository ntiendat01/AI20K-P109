from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from ocr.ocr_service import engine as ocr_engine
from ocr.ocr_service.main import create_app
from ocr.ocr_service.settings import OCRServiceSettings
from src.infrastructure.ocr.contracts import OCRLine, OCRPage


class FakeEngine:
    def __init__(self, _settings: OCRServiceSettings):
        self.warmed_up = False

    def warm_up(self) -> None:
        self.warmed_up = True

    def extract(self, _document: bytes, _suffix: str) -> list[OCRPage]:
        return [OCRPage(page_number=1, raw_text="Báo giá", lines=[OCRLine(text="Báo giá", confidence=0.98)])]


def test_paddle_ocr_loads_only_detection_and_recognition_by_default(monkeypatch) -> None:
    options = []
    monkeypatch.setattr(
        ocr_engine,
        "import_module",
        lambda _name: SimpleNamespace(PaddleOCR=lambda **kwargs: options.append(kwargs) or object()),
    )

    ocr_engine.PaddleOCREngine(OCRServiceSettings()).warm_up()

    assert options == [
        {
            "lang": "vi",
            "ocr_version": "PP-OCRv3",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "enable_mkldnn": False,
        }
    ]


def _client(*, max_upload_bytes: int = 1024, token: str = "") -> TestClient:
    app = create_app(
        settings=OCRServiceSettings(ocr_max_upload_bytes=max_upload_bytes, ocr_service_token=token),
        engine_factory=FakeEngine,
    )
    return TestClient(app)


def test_ocr_service_returns_versioned_page_payload() -> None:
    with _client() as client:
        response = client.post(
            "/v1/ocr",
            files={"document": ("quote.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
            headers={"X-Request-ID": "request-123"},
        )

    assert response.status_code == 200
    assert response.json()["request_id"] == "request-123"
    assert response.json()["pages"][0]["lines"][0]["confidence"] == 0.98


def test_ocr_service_rejects_oversized_documents() -> None:
    with _client(max_upload_bytes=8) as client:
        response = client.post(
            "/v1/ocr",
            files={"document": ("quote.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
        )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_ocr_service_requires_token_when_configured() -> None:
    with _client(token="service-secret") as client:
        response = client.post(
            "/v1/ocr",
            files={"document": ("quote.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
        )

    assert response.status_code == 401
