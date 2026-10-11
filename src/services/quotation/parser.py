"""Best-effort extraction for text and PDF quotations.

Real supplier PDFs are rarely machine-readable as one neat CSV row. This
parser handles both table extraction (pdfplumber) and the common PDF text
layout where each visual table column is emitted on a separate line.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

from src.extraction.pdf_extractor import extract_pdf
from src.extraction.quotation_parser import parse_quotation
from src.models.quotation.confirmation import QuotationItem

MAX_PDF_PAGES = 10
EXTRACTION_VERSION = 4
MONEY_PATTERN = re.compile(r"(?:\d{1,3}(?:[,.\s]\d{3})+|\d+)(?:[,.]\d{1,2})?")
ROW_NUMBER_PATTERN = re.compile(r"^\d{1,4}$")
PRICE_LIST_PATTERN = re.compile(r"(?:bảng\s*giá|price\s*list|đơn\s*giá\s*(?:bán\s*)?(?:lẻ|sỉ|đại\s*lý))", re.IGNORECASE)
COMPANY_NAME_PATTERN = re.compile(
    r"((?:công\s*ty|cty|company)\s+(?:cổ\s*phần|tnhh|trách\s*nhiệm\s*hữu\s*hạn|cp)\b[^\n\r]*)",
    re.IGNORECASE,
)


@dataclass
class ExtractedQuotation:
    supplier_name: str = ""
    delivery_time: str = ""
    payment_terms: str = ""
    warranty: str = ""
    currency: str = ""
    items: list[QuotationItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -:•\t")


def _clean_warranty(value: str) -> str:
    cleaned = _clean(value)
    # Loại bỏ các tiền tố thừa thường xuất hiện sau từ khóa Bảo hành như "& Chất lượng:", "và Dịch vụ:"
    cleaned = re.sub(
        r"^(?:&|và|\+)?\s*(?:chất\s*lượng|dịch\s*vụ|cam\s*kết)\s*[:：\-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip(" -:•\t")
    return cleaned


def _find_value(text: str, labels: str) -> str:
    """Find a label's value on its own, inline, or immediately following line."""
    inline = re.search(
        rf"^[\t •·*\-]*(?:{labels})(?:[ \t]*[:：\-][ \t]*|[ \t]+)(\S[^\n\r]*)[ \t]*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if inline:
        return _clean(inline.group(1))
    next_line = re.search(
        rf"^[\t •·*\-]*(?:{labels})[ \t]*\r?\n[ \t]*(\S[^\n\r]*)[ \t]*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return _clean(next_line.group(1)) if next_line else ""


def _parse_money(value: str) -> Decimal | None:
    candidate = _clean(value).replace(" ", "")
    if not candidate:
        return None
    digits = "".join(re.findall(r"\d", candidate))
    if not digits:
        return None
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _looks_like_money(value: str) -> bool:
    return bool(MONEY_PATTERN.fullmatch(_clean(value).replace(" ", "")))


def _is_summary(value: str) -> bool:
    return bool(re.search(r"subtotal|grand\s*total|total\b|vat|thuế|tổng\s*cộng", value, re.IGNORECASE))


def _make_item(
    *,
    product_name: str,
    product_code: str = "",
    unit: str = "",
    quantity_value: str,
    unit_price_value: str,
    total_value: str,
) -> QuotationItem | None:
    quantity = _parse_money(quantity_value)
    unit_price = _parse_money(unit_price_value)
    line_total = _parse_money(total_value)
    if not product_name or not quantity or not unit_price or not line_total:
        return None
    try:
        return QuotationItem(
            product_name=_clean(product_name),
            product_code=_clean(product_code),
            unit=_clean(unit),
            quantity=int(quantity),
            unit_price=unit_price,
            line_total=line_total,
        )
    except (ValueError, OverflowError):
        return None


def _parse_delimited_item_row(line: str) -> QuotationItem | None:
    cells = [_clean(cell) for cell in re.split(r"\s*[|;]\s*", line) if _clean(cell)]
    if len(cells) < 4 or _is_summary(" ".join(cells)):
        return None
    header_text = " ".join(cells).lower()
    if any(label in header_text for label in ("số lượng", "quantity", "đơn giá", "unit price", "amount")):
        return None
    if len(cells) >= 6:
        # Common quotation format: No. | description | quantity | unit |
        # unit price | amount.  The old parser treated ``unit`` as quantity.
        return _make_item(
            product_code=cells[0],
            product_name=" ".join(cells[1:-4]),
            quantity_value=cells[-4],
            unit=cells[-3],
            unit_price_value=cells[-2],
            total_value=cells[-1],
        )
    return _make_item(
        product_code=cells[0] if len(cells) == 5 else "",
        product_name=cells[1] if len(cells) == 5 else cells[0],
        quantity_value=cells[-3],
        unit_price_value=cells[-2],
        total_value=cells[-1],
    )


def _extract_vertical_items(text: str) -> list[QuotationItem]:
    """Extract rows from PDF text laid out as STT, description, qty, unit, prices."""
    lines = [_clean(line) for line in text.splitlines() if _clean(line)]
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.fullmatch(r"(?:no\.?|stt|l/i)", line, flags=re.IGNORECASE)
            or ("item" in line.lower() and "description" in line.lower())
        ),
        -1,
    )
    if header_index < 0:
        return []

    items: list[QuotationItem] = []
    index = header_index + 1
    while index < len(lines):
        if _is_summary(lines[index]):
            break
        if not ROW_NUMBER_PATTERN.fullmatch(lines[index]):
            index += 1
            continue

        row_number = lines[index]
        cursor = index + 1
        description: list[str] = []
        while cursor < len(lines):
            if (
                description
                and ROW_NUMBER_PATTERN.fullmatch(lines[cursor])
                and cursor + 3 < len(lines)
                and not _looks_like_money(lines[cursor + 1])
                and _looks_like_money(lines[cursor + 2])
                and _looks_like_money(lines[cursor + 3])
            ):
                item = _make_item(
                    product_code=row_number,
                    product_name=" ".join(description),
                    quantity_value=lines[cursor],
                    unit=lines[cursor + 1],
                    unit_price_value=lines[cursor + 2],
                    total_value=lines[cursor + 3],
                )
                if item:
                    items.append(item)
                index = cursor + 4
                break
            if ROW_NUMBER_PATTERN.fullmatch(lines[cursor]):
                # A new row started before this row matched the expected
                # quantity/unit/price/total shape.
                index = cursor
                break
            if _is_summary(lines[cursor]):
                return items
            description.append(lines[cursor])
            cursor += 1
        else:
            index += 1
            continue
        if cursor >= len(lines):
            index += 1
    return items


def _extract_text_from_pdf(content: bytes) -> str:
    """Extract readable text and table rows, preferring pdfplumber for tables."""
    try:
        import pdfplumber
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError as error:  # pragma: no cover - dependency is required in production
            raise ValueError("PDF parser chưa được cài đặt trên máy chủ.") from error

        reader = PdfReader(BytesIO(content))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF vượt quá giới hạn {MAX_PDF_PAGES} trang.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    with pdfplumber.open(BytesIO(content)) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF vượt quá giới hạn {MAX_PDF_PAGES} trang.")
        parts: list[str] = []
        for page in pdf.pages:
            if text := page.extract_text():
                parts.append(text)
            for table in page.extract_tables():
                for row in table:
                    cells = [_clean(cell or "") for cell in row]
                    if any(cells):
                        parts.append(" | ".join(cells))
        return "\n".join(parts)


def _deduplicate(items: list[QuotationItem]) -> list[QuotationItem]:
    seen: set[tuple[str, int, Decimal, Decimal]] = set()
    result: list[QuotationItem] = []
    for item in items:
        key = (item.product_name.lower(), item.quantity, item.unit_price, item.line_total)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _to_review_item(item: object, *, catalog_price_list: bool = False) -> QuotationItem | None:
    """Convert the provenance-rich extractor item to the editable UI model."""
    raw_name = getattr(item, "raw_name", None)
    raw_description = getattr(item, "raw_description", None)
    quantity = getattr(item, "quantity", None)
    unit_price = getattr(item, "unit_price", None)
    total_price = getattr(item, "total_price", None)
    if not raw_name or unit_price is None:
        return None

    # Catalogues often publish one or two unit-price columns but intentionally
    # omit order quantity and line total. Keep them reviewable as a quantity-1
    # draft rather than silently discarding every row. The warning below tells
    # procurement to verify MOQ and enter the actual order quantity.
    if (quantity is None or total_price is None) and not catalog_price_list:
        return None
    if catalog_price_list:
        quantity = quantity if quantity is not None else 1
        total_price = total_price if total_price is not None else unit_price

    quantity_decimal = Decimal(str(quantity))
    if quantity_decimal != quantity_decimal.to_integral_value():
        return None
    name_parts = [_clean(raw_name)]
    if raw_description and _clean(raw_description) not in name_parts:
        name_parts.append(_clean(raw_description))
    try:
        return QuotationItem(
            product_name=" ".join(name_parts),
            unit=_clean(getattr(item, "unit", "") or ""),
            quantity=int(quantity_decimal),
            unit_price=Decimal(str(unit_price)),
            line_total=Decimal(str(total_price)),
        )
    except (ArithmeticError, ValueError):
        return None


def _add_missing_field_warnings(extracted: ExtractedQuotation) -> ExtractedQuotation:
    if not extracted.supplier_name:
        extracted.warnings.append("Chưa nhận diện được tên nhà cung cấp; hãy kiểm tra và sửa trước khi xác nhận.")
    if not extracted.items:
        extracted.warnings.append("Không nhận diện được dòng hàng; hãy thêm hoặc sửa thủ công trước khi xác nhận.")
    if not extracted.delivery_time:
        extracted.warnings.append("Chưa nhận diện thời gian giao hàng.")
    if not extracted.payment_terms:
        extracted.warnings.append("Chưa nhận diện điều khoản thanh toán.")
    return extracted


def _supplier_from_company_header(text: str) -> str:
    """Recover a supplier name from common Vietnamese company letterheads."""
    match = COMPANY_NAME_PATTERN.search(text)
    if not match:
        return ""
    tokens = _clean(match.group(1)).split()
    # Some PDFs place the company logo text after the letterhead on the same
    # extracted line (for example, "AN PHÁT AN PHÁT"). Remove only an exact
    # repeated ending; the source text remains available for user review.
    for size in range(min(4, len(tokens) // 2), 0, -1):
        if tokens[-size:] == tokens[-2 * size : -size]:
            tokens = tokens[:-size]
            break
    return " ".join(tokens)


def _extract_pdf_quotation(content: bytes) -> ExtractedQuotation:
    """Use the PyMuPDF pipeline, retaining PDF table-cell boundaries."""
    try:
        document = extract_pdf(content)
    except ValueError as error:
        # A blank but valid PDF remains reviewable: the procurement user can
        # enter the fields manually.  Broken PDFs and OCR failures still fail.
        if str(error) != "PDF không có nội dung có thể trích xuất.":
            raise
        return _add_missing_field_warnings(ExtractedQuotation())
    parsed = parse_quotation(document)
    text = "\n".join(page.text for page in document.pages)
    catalog_price_list = bool(PRICE_LIST_PATTERN.search(text))
    items = [
        review_item
        for item in parsed.items
        if (review_item := _to_review_item(item, catalog_price_list=catalog_price_list))
    ]
    extracted = ExtractedQuotation(
        # Some supplier PDFs use ``Supplier Name`` without a colon.  The
        # compatibility lookup covers that layout until the structured parser
        # sees every supplier variant.
        supplier_name=(
            parsed.supplier_name
            or _find_value(text, r"nhà\s*cung\s*cấp|ncc|supplier")
            or _supplier_from_company_header(text)
        ),
        delivery_time=_find_value(
            text,
            r"(?:thời\s*gian\s*)?giao(?:\s*hàng)?|đáp\s*ứng|delivery(?:\s*(?:terms?|time))?",
        ),
        payment_terms=_find_value(text, r"(?:điều\s*khoản\s*)?thanh\s*toán|payment(?:\s*terms?)?"),
        warranty=_clean_warranty(
            _find_value(
                text,
                r"bảo\s*hành(?:\s*(?:&|và|\+)\s*(?:chất\s*lượng|dịch\s*vụ|cam\s*kết))?|warranty",
            )
        ),
        currency=parsed.currency or _find_value(text, r"tiền\s*tệ|currency"),
        items=_deduplicate(items),
        warnings=list(document.warnings),
    )
    if catalog_price_list and items:
        extracted.warnings.append(
            "Đây là bảng giá: hệ thống đặt số lượng mặc định là 1 và thành tiền bằng đơn giá. "
            "Hãy kiểm tra MOQ và sửa số lượng theo nhu cầu trước khi xác nhận."
        )
        if re.search(r"đơn\s*giá\s*bán", text, re.IGNORECASE) and re.search(
            r"đơn\s*giá\s*(?:sỉ|đại\s*lý)", text, re.IGNORECASE
        ):
            extracted.warnings.append(
                "Bảng giá có nhiều cột giá; hiện đang dùng cột đơn giá bán lẻ. Hãy đối chiếu điều kiện mua sỉ/đại lý."
            )
    if len(items) != len(parsed.items):
        extracted.warnings.append("Một số dòng hàng thiếu số lượng hoặc giá; cần kiểm tra.")
    return _add_missing_field_warnings(extracted)


def extract_quotation(content: bytes, suffix: str) -> ExtractedQuotation:
    """Extract a reviewable draft; human confirmation is required before use."""
    if suffix == ".pdf":
        return _extract_pdf_quotation(content)

    text = content.decode("utf-8", errors="replace")
    extracted = ExtractedQuotation(
        supplier_name=_find_value(text, r"nhà\s*cung\s*cấp|ncc|supplier"),
        delivery_time=_find_value(text, r"thời\s*gian\s*giao(?:\s*hàng)?|delivery(?:\s*(?:terms?|time))?"),
        payment_terms=_find_value(text, r"điều\s*khoản\s*thanh\s*toán|payment(?:\s*terms?)?"),
        warranty=_clean_warranty(
            _find_value(
                text,
                r"bảo\s*hành(?:\s*(?:&|và|\+)\s*(?:chất\s*lượng|dịch\s*vụ|cam\s*kết))?|warranty",
            )
        ),
        currency=_find_value(text, r"tiền\s*tệ|currency"),
    )
    delimited_items = [item for line in text.splitlines() if (item := _parse_delimited_item_row(line))]
    extracted.items = _deduplicate(delimited_items or _extract_vertical_items(text))
    return _add_missing_field_warnings(extracted)
