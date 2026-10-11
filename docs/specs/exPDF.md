# Task: Implement Document Extraction MVP for Procurement Comparison

## Context

We are building a Procurement Comparison Agent.

The final product will accept 4–5 supplier quotation PDFs simultaneously and compare them without requiring a reference quotation.

For this task, DO NOT implement AI product matching or supplier comparison yet.

The current milestone is only:

> PDF quotation → extract structured data → return validated Quotation JSON

The extraction layer must be designed so that a future AI normalization/matching layer can consume its output without changing the extraction architecture.

---

## Goal

Implement a `Document Extraction` module in the existing backend.

The module must:

1. Accept a PDF file.
2. Detect whether the PDF contains an actual text layer.
3. For text-based PDFs:
   - extract text and tables without OCR when possible.
4. For scanned/image-based PDFs:
   - use OCR as a fallback.
5. Extract quotation-level information.
6. Extract quotation line items.
7. Validate the result with Pydantic.
8. Return a stable structured JSON schema.
9. Preserve the original extracted values in `raw_*` fields.
10. Never invent missing values.

Do not implement product matching yet.

---

# Expected Architecture

Create a clean module similar to:

```text
data/
├── extraction/
│   ├── __init__.py
│   ├── detector.py
│   ├── pdf_extractor.py
│   ├── ocr_extractor.py
│   └── quotation_parser.py
│
├── models/
│   └── quotation.py
│
└── api/
    └── ...
```

Adapt the structure to the existing project if a different architecture already exists.

Do NOT blindly create duplicate architecture.

First inspect the existing repository and reuse existing conventions.

---

# Technology

Use Python.

Preferred libraries:

- PyMuPDF (`fitz`) for PDF inspection and text extraction.
- Docling for document/table extraction where appropriate.
- Tesseract OCR as fallback for scanned PDFs.
- Pydantic for validation.

Before installing anything:

1. Inspect `requirements.txt`.
2. Inspect the existing Dockerfile.
3. Inspect the existing Python version.
4. Reuse already installed dependencies where possible.

Do not introduce unnecessary dependencies.

If Docling or Tesseract requires Docker/system packages, update the Docker setup appropriately and explain why.

---

# 1. PDF Type Detection

Implement:

```python
def detect_pdf_type(file_path: str) -> str:
    ...
```

Possible results:

```text
"text"
"scanned"
"mixed"
```

Basic rule:

- If pages contain meaningful text → `text`
- If pages contain mostly images and little/no text → `scanned`
- If some pages contain text and others are scanned → `mixed`

Do not rely only on file metadata.

---

# 2. Text Extraction

For text PDFs, extract:

- page text
- tables if available
- page number/source information if practical

Do not OCR a text PDF unnecessarily.

Preserve the extracted text because it will be useful for debugging.

---

# 3. OCR Fallback

For scanned PDFs:

```text
PDF
 ↓
Render page to image
 ↓
OCR
 ↓
Extract text
```

Use Tesseract for the MVP.

The implementation should support Vietnamese and English if the required Tesseract language packs are available.

If Vietnamese OCR data is unavailable inside the container, document the required package/configuration instead of silently falling back to English.

---

# 4. Pydantic Models

Create the following models.

## QuotationItem

```python
class QuotationItem(BaseModel):
    raw_name: str | None = None
    raw_description: str | None = None

    quantity: float | None = None
    unit: str | None = None

    unit_price: float | None = None
    total_price: float | None = None

    currency: str | None = None
```

Add useful fields if required by the existing implementation, but do not over-engineer the schema.

## Quotation

```python
class Quotation(BaseModel):
    supplier_name: str | None = None
    quotation_number: str | None = None
    quotation_date: str | None = None

    currency: str | None = None

    subtotal: float | None = None
    discount: float | None = None
    vat_rate: float | None = None
    vat_amount: float | None = None
    grand_total: float | None = None

    items: list[QuotationItem] = []
```

Important:

Missing information must remain `None`.

Do NOT convert missing prices into `0`.

---

# 5. Preserve Raw Data

This is important.

Do not normalize product names at this stage.

Example:

Input:

```text
Dell Latitude 5450 Laptop
```

Output:

```json
{
  "raw_name": "Dell Latitude 5450 Laptop"
}
```

Do NOT change it to:

```text
Dell Latitude 5450
```

Normalization will be handled by a future AI layer.

The extraction layer should preserve the supplier's original wording as much as possible.

---

# 6. Quotation Parser

Implement a parser that converts extracted document content into:

```python
Quotation
```

The parser should attempt to identify:

### Quotation metadata

- supplier name
- quotation number
- quotation date
- currency

### Line items

- item name
- description
- quantity
- unit
- unit price
- total price

### Financial summary

- subtotal
- discount
- VAT
- grand total

The parser must tolerate missing fields.

Do not require every quotation to contain every field.

---

# 7. Multiple Files

Add an endpoint or service that can process multiple PDFs.

Example:

```javascript
POST /api/comparisons/{comparison_id}/extract
```

Input:

```text
files[]
```

The service should process each quotation independently.

Example result:

```json
{
  "quotations": [
    {
      "file_name": "supplier_a.pdf",
      "data": {
        "supplier_name": "ABC Technology",
        "quotation_number": "ABC-2026-0918",
        "items": []
      }
    },
    {
      "file_name": "supplier_b.pdf",
      "data": {
        "supplier_name": "VietTech",
        "quotation_number": "VT-2026-0918",
        "items": []
      }
    }
  ]
}
```

One failed document should not crash the entire batch.

Return per-file processing status.

Example:

```json
{
  "file_name": "supplier_c.pdf",
  "status": "failed",
  "error": "Unable to extract quotation data"
}
```

---

# 8. Extraction Status

Use clear statuses:

```text
pending
processing
completed
failed
needs_review
```

Do not hide extraction failures.

---

# 9. API Response

The API should return enough information for the frontend to display an extraction preview.

Example:

```json
{
  "file_name": "abc_quote.pdf",
  "status": "completed",
  "document_type": "text",
  "quotation": {
    "supplier_name": "ABC Technology",
    "quotation_number": "ABC-2026-0918",
    "quotation_date": "2026-09-18",
    "currency": "VND",
    "items": [
      {
        "raw_name": "Dell Latitude 5450 Laptop",
        "raw_description": "Ultra 5 / 16GB / 512GB SSD",
        "quantity": 10,
        "unit": "pcs",
        "unit_price": 24500000,
        "total_price": 245000000,
        "currency": "VND"
      }
    ]
  }
}
```

---

# 10. Error Handling

Handle at minimum:

- invalid PDF
- empty PDF
- corrupted PDF
- scanned PDF
- PDF with no extractable content
- table extraction failure
- OCR failure
- invalid numeric values
- unsupported file type

Do not crash the API because one quotation fails.

---

# 11. Numeric Parsing

Quotation numbers may appear as:

```text
24,500,000
24.500.000
24 500 000
24.500.000,00
```

Implement a small utility for safely parsing monetary values.

Do not blindly replace all `.` and `,`.

Document the assumptions.

If a number cannot be reliably parsed:

```json
{
  "unit_price": null
}
```

rather than guessing.

---

# 12. Testing

Create tests for at least:

### Test 1

Clean text-based quotation PDF.

### Test 2

Table-based quotation.

### Test 3

Scanned quotation.

### Test 4

Quotation with missing fields.

### Test 5

Quotation with different numeric formatting.

### Test 6

Multiple quotation files.

### Test 7

One valid PDF + one corrupted PDF.

The tests should verify the resulting Pydantic models.

Use fixtures rather than hardcoding production paths.

---

# 13. Do NOT implement

Do not implement:

- AI product matching
- canonical product generation
- similarity scoring
- supplier ranking
- cheapest supplier selection
- negotiation
- recommendation
- winner selection
- LLM-based normalization

Those belong to the next milestone.

---

# 14. Definition of Done

The task is complete when:

1. Backend starts successfully in Docker.
2. A PDF can be uploaded.
3. The system detects text/scanned/mixed PDFs.
4. Text PDFs are extracted without unnecessary OCR.
5. Scanned PDFs use OCR fallback.
6. A quotation is converted into validated Pydantic data.
7. Multiple PDFs can be processed in one request.
8. One failed PDF does not fail the entire batch.
9. Missing values remain `None`.
10. Original item names/descriptions are preserved.
11. Automated tests pass.
12. Existing project functionality is not broken.

---

# Final implementation principle

Keep this layer deterministic and modular.

The intended future pipeline is:

```text
PDF
 ↓
Document Extraction        ← THIS TASK
 ↓
Quotation JSON
 ↓
AI Normalization           ← FUTURE
 ↓
Global Item Matching       ← FUTURE
 ↓
Canonical Item Groups      ← FUTURE
 ↓
Comparison Matrix          ← FUTURE
```

Do not mix future AI matching logic into the extraction implementation.
Before making changes, inspect the existing repository, current API structure, Docker setup, and dependency management. Then implement the smallest clean change that satisfies this specification.
