"""Conservative rules for mapping extracted document content to quotation JSON."""

import re

from src.extraction.pdf_extractor import ExtractedDocument
from src.models.quotation.extraction import ExtractedQuotation as Quotation
from src.models.quotation.extraction import ExtractedQuotationItem as QuotationItem

NUMBER = re.compile(r"^[+-]?\d[\d., \u00a0]*$")
SUMMARY_LABELS = {
    "subtotal": r"(?:subtotal|tạm\s*tính|cộng\s*tiền\s*hàng)",
    "discount": r"(?:discount|chiết\s*khấu|giảm\s*giá)",
    "vat_amount": r"(?:vat|thuế\s*gtgt|thuế\s*vat)(?!\s*rate)",
    "grand_total": r"(?:grand\s*total|total\s*due|tổng\s*cộng|tổng\s*thanh\s*toán)",
}
HEADERS = {
    "description": r"(?:description|chi\s*tiết|specification|thông\s*số|details?)",
    "name": r"(?:tên\s*(?:hàng|sản\s*phẩm)|mô\s*tả|mặt\s*hàng|quy\s*cách|product|item\s*name|hàng\s*hóa)",
    "quantity": r"(?:số\s*lượng|sl|qty|quantity)",
    "unit_price": r"(?:đơn\s*giá|unit\s*price|price\s*/\s*unit)",
    "total_price": r"(?:thành\s*tiền|amount|line\s*total|total\s*price)",
    "unit": r"(?:đơn\s*vị|đvt|unit|uom)",
}


def parse_number(value: str | None) -> float | None:
    """Parse unambiguous monetary formats; ambiguous single separators stay null.

    Space-separated groups and repeated 3-digit separators are thousands.
    With both punctuation marks, the last mark is decimal only when followed
    by one or two digits. One punctuation mark with 1–2 trailing digits is a
    decimal; a single 3-digit group is treated as thousands. Other shapes are
    rejected rather than guessed.
    """
    if value is None:
        return None
    candidate = value.strip().replace("\u00a0", " ")
    if not NUMBER.fullmatch(candidate):
        return None
    sign = -1 if candidate.startswith("-") else 1
    candidate = candidate.lstrip("+-")
    if " " in candidate:
        if not re.fullmatch(r"\d{1,3}(?: \d{3})+(?:[,.]\d{1,2})?", candidate):
            return None
        candidate = candidate.replace(" ", "")
    marks = [(i, char) for i, char in enumerate(candidate) if char in ".,"]
    if not marks:
        return sign * float(candidate)
    last_index, last_mark = marks[-1]
    tail = candidate[last_index + 1 :]
    decimal = len(tail) in {1, 2}
    integer_part = candidate[:last_index] if decimal else candidate
    if not integer_part:
        return None
    parts = re.split(r"[,.]", integer_part)
    if len(parts) > 1 and not (1 <= len(parts[0]) <= 3 and all(len(part) == 3 for part in parts[1:])):
        return None
    if not decimal and (len(tail) != 3 or len(parts) == 1):
        return None
    if decimal and last_mark in integer_part:
        return None
    return sign * float("".join(parts) + ("." + tail if decimal else ""))


def _label_value(text: str, labels: str) -> str | None:
    pattern = rf"^\s*(?:{labels})(?:[ \t]*[:：#][ \t]*|[ \t]+-[ \t]+|[ \t]+)(\S[^\n]*)$"
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(rf"^\s*(?:{labels})\s*$\n\s*(\S[^\n]*)", text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def _currency(text: str) -> str | None:
    labelled = _label_value(text, r"currency|tiền\s*tệ|đơn\s*vị\s*tiền")
    sample = labelled or text
    match = re.search(r"\b(?:VND|VNĐ|USD|EUR)\b", sample, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _summary(text: str, label: str) -> float | None:
    pattern = SUMMARY_LABELS[label]
    for line in text.splitlines():
        if re.search(pattern, line, re.IGNORECASE):
            values = re.findall(r"(?<!\w)[+-]?\d[\d., \u00a0]*", line)
            parsed = [parse_number(value) for value in values]
            parsed = [value for value in parsed if value is not None]
            if parsed:
                return parsed[-1]
    return None


def _header_map(row: list[str]) -> dict[str, int]:
    mapping = {}
    for index, cell in enumerate(row):
        for key, pattern in HEADERS.items():
            if key not in mapping and re.search(pattern, cell, re.IGNORECASE):
                mapping[key] = index
                break
    if "name" not in mapping and "description" in mapping:
        mapping["name"] = mapping.pop("description")
    return mapping if "name" in mapping and ("unit_price" in mapping or "total_price" in mapping) else {}


def _cell(row: list[str], mapping: dict[str, int], key: str) -> str | None:
    index = mapping.get(key)
    if index is None or index >= len(row):
        return None
    return row[index].strip() or None


def _table_items(document: ExtractedDocument, currency: str | None) -> list[QuotationItem]:
    items = []
    for page_number, table in document.tables:
        header_index, mapping = next(((i, m) for i, row in enumerate(table) if (m := _header_map(row))), (-1, {}))
        if header_index < 0:
            continue
        for row in table[header_index + 1 :]:
            name = _cell(row, mapping, "name")
            if not name or any(re.search(pattern, name, re.IGNORECASE) for pattern in SUMMARY_LABELS.values()):
                continue
            items.append(
                QuotationItem(
                    raw_name=name,
                    raw_description=_cell(row, mapping, "description"),
                    quantity=parse_number(_cell(row, mapping, "quantity")),
                    unit=_cell(row, mapping, "unit"),
                    unit_price=parse_number(_cell(row, mapping, "unit_price")),
                    total_price=parse_number(_cell(row, mapping, "total_price")),
                    currency=currency,
                    source_page=page_number,
                )
            )
    return items


def _delimited_items(document: ExtractedDocument, currency: str | None) -> list[QuotationItem]:
    items = []
    for page in document.pages:
        lines = page.text.splitlines()
        mapping: dict[str, int] = {}
        for line in lines:
            if "|" not in line and ";" not in line:
                continue
            cells = [cell.strip() for cell in re.split(r"\s*[|;]\s*", line)]
            if header := _header_map(cells):
                mapping = header
                continue
            if not mapping:
                continue
            name = _cell(cells, mapping, "name")
            if not name or any(re.search(pattern, name, re.IGNORECASE) for pattern in SUMMARY_LABELS.values()):
                continue
            items.append(
                QuotationItem(
                    raw_name=name,
                    raw_description=_cell(cells, mapping, "description"),
                    quantity=parse_number(_cell(cells, mapping, "quantity")),
                    unit=_cell(cells, mapping, "unit"),
                    unit_price=parse_number(_cell(cells, mapping, "unit_price")),
                    total_price=parse_number(_cell(cells, mapping, "total_price")),
                    currency=currency,
                    source_page=page.page_number,
                )
            )
    return items


def parse_quotation(document: ExtractedDocument) -> Quotation:
    text = "\n".join(page.text for page in document.pages)
    currency = _currency(text)
    items = _table_items(document, currency) or _delimited_items(document, currency)
    vat_rate = None
    vat_match = re.search(r"(?:vat|thuế\s*(?:gtgt|vat))\s*\(?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%", text, re.IGNORECASE)
    if vat_match:
        vat_rate = parse_number(vat_match.group(1))
    return Quotation(
        supplier_name=_label_value(text, r"supplier|nhà\s*cung\s*cấp|ncc|bên\s*bán"),
        quotation_number=_label_value(
            text, r"quotation\s*(?:no\.?|number|#)|quote\s*(?:no\.?|number|#)|số\s*báo\s*giá"
        ),
        quotation_date=_label_value(text, r"quotation\s*date|quote\s*date|ngày\s*báo\s*giá|date"),
        currency=currency,
        subtotal=_summary(text, "subtotal"),
        discount=_summary(text, "discount"),
        vat_rate=vat_rate,
        vat_amount=_summary(text, "vat_amount"),
        grand_total=_summary(text, "grand_total"),
        items=items,
    )
