"""Independent per-file quotation extraction for synchronous preview requests."""

import logging

from src.domain.quotation.extraction import ExtractionResult, ExtractionStatus
from src.infrastructure.documents.pdf_extractor import extract_pdf
from src.infrastructure.documents.quotation_parser import parse_quotation

logger = logging.getLogger(__name__)


def process_pdf(file_name: str, content: bytes) -> ExtractionResult:
    try:
        document = extract_pdf(content)
        quotation = parse_quotation(document)
        warnings = list(document.warnings)
        if not quotation.supplier_name:
            warnings.append("Chưa nhận diện được nhà cung cấp.")
        if not quotation.items:
            warnings.append("Chưa nhận diện được dòng hàng.")
        elif any(
            item.quantity is None or item.unit_price is None or item.total_price is None for item in quotation.items
        ):
            warnings.append("Một số dòng hàng thiếu số lượng hoặc giá; cần kiểm tra.")
        status = ExtractionStatus.NEEDS_REVIEW if warnings else ExtractionStatus.COMPLETED
        return ExtractionResult(
            file_name=file_name,
            status=status,
            document_type=document.document_type,
            quotation=quotation,
            pages=document.pages,
            warnings=warnings,
        )
    except ValueError as error:
        logger.warning(
            "PDF extraction rejected invalid document",
            extra={
                "event": "pdf_extraction_failed",
                "error_type": type(error).__name__,
                "file_name": file_name,
                "storage_backend": "filesystem",
            },
        )
        return ExtractionResult(file_name=file_name, status=ExtractionStatus.FAILED, error=str(error))
    except Exception:
        logger.exception("Unexpected PDF extraction failure: %s", file_name)
        return ExtractionResult(
            file_name=file_name,
            status=ExtractionStatus.FAILED,
            error="Không thể trích xuất dữ liệu báo giá.",
        )
