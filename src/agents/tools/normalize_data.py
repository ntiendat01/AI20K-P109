"""Deterministic normalization tool for UOM and currency conversion.

Converts quotation line items to a common unit of measure and currency
using fixed lookup tables.  When a UOM is unknown the item is flagged
for manual conversion — the system never guesses (US-03.1a-AC3).
"""

from __future__ import annotations

from collections.abc import Mapping

# ---------------------------------------------------------------------------
# UOM conversion table
# ---------------------------------------------------------------------------
# Mapping: (source_uom_lowercase) -> (base_uom, multiplier)
# Interpretation: 1 <source_uom> = <multiplier> <base_uom>
#
# All base units are normalised to their smallest common form.
# E.g. 1 "hộp" = 10 "cái", 1 "thùng" = 200 "cái", 1 "tá" = 12 "cái".
#
# Units that are already the base unit map to multiplier 1.
# ---------------------------------------------------------------------------

UOM_CONVERSION_TABLE: dict[str, tuple[str, float]] = {
    # --- Counting units ---
    "cái": ("cái", 1),
    "chiếc": ("cái", 1),
    "ea": ("cái", 1),  # "each" in English quotations
    "pcs": ("cái", 1),
    "hộp": ("cái", 10),
    "thùng": ("cái", 200),  # 1 thùng = 20 hộp = 200 cái
    "tá": ("cái", 12),
    # --- Weight units ---
    "kg": ("kg", 1),
    "g": ("kg", 0.001),
    "tấn": ("tấn", 1),
    "tn": ("tấn", 1),  # viết tắt tấn
    "tan": ("tấn", 1),
    "mt": ("tấn", 1),  # metric ton / metric tonne on supplier quotations
    "metric ton": ("tấn", 1),
    "metric tonne": ("tấn", 1),
    # --- Length units ---
    "m": ("m", 1),
    "mét": ("m", 1),
    "cm": ("m", 0.01),
    "mm": ("m", 0.001),
    # --- Volume units ---
    "lít": ("lít", 1),
    "ml": ("lít", 0.001),
    # --- Pass-through packaging units (same base as themselves) ---
    "cuộn": ("cuộn", 1),
    "cuộn/100c": ("cuộn/100c", 1),
    "cây": ("cây", 1),
    "bao": ("bao", 1),
    "thanh": ("thanh", 1),
    "bộ": ("bộ", 1),
}

# ---------------------------------------------------------------------------
# Currency exchange rates (to VND)
# ---------------------------------------------------------------------------
# Rates are static / configurable; in production these could come from
# a config file or external API.
# ---------------------------------------------------------------------------

FX_RATES_TO_VND: dict[str, float] = {
    "VND": 1.0,
    "VNĐ": 1.0,  # alternate Vietnamese notation
    "USD": 25_400.0,
    "EUR": 27_500.0,
    "JPY": 170.0,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_items(
    items: list[dict[str, object]],
    target_uom: str,
    target_currency: str,
) -> list[dict[str, object]]:
    """Normalize a list of line-item dicts to *target_uom* and *target_currency*.

    Each input item is expected to contain at least:
        - ``unit`` / ``uom``  : original unit of measure (str)
        - ``unit_price``      : original unit price (numeric or numeric-string)
        - ``quantity``        : original quantity (numeric)
        - ``currency``        : original currency code (str)
        - ``product_name`` / ``item_name`` : descriptive name (str)

    Returns a list of enriched dicts — one per input item — containing both
    the original values and the normalised values.
    """

    normalized: list[dict[str, object]] = []

    for item in items:
        normalized.append(_normalize_single_item(item, target_uom, target_currency))

    return normalized


def normalize_supplier(
    supplier: dict[str, object],
    target_uom: str,
    target_currency: str,
) -> dict[str, object]:
    """Normalize all line items for a single supplier extraction.

    Parameters
    ----------
    supplier:
        A supplier dict as stored in ``raw_extractions``.  Must contain an
        ``"items"`` key holding a list of line-item dicts.
    target_uom:
        The desired unit of measure for comparison (e.g. ``"cái"``).
    target_currency:
        The desired currency code (e.g. ``"VND"``).

    Returns
    -------
    dict with:
        - ``supplier_id``: forwarded from input (falls back to ``supplier_name``).
        - ``items``: list of normalised item dicts.
        - ``has_manual_conversion``: ``True`` if *any* item requires manual conversion.
    """

    items_value = supplier.get("items")
    raw_items = (
        [dict(item) for item in items_value if isinstance(item, Mapping)] if isinstance(items_value, list) else []
    )
    supplier_id = (
        supplier.get("supplier_id")
        or supplier.get("supplier")
        or supplier.get("supplier_name")
        or supplier.get("id", "unknown")
    )

    normalized_items = normalize_items(raw_items, target_uom, target_currency)
    has_manual = any(bool(it.get("requires_manual_conversion")) for it in normalized_items)

    return {
        "supplier_id": supplier_id,
        "items": normalized_items,
        "has_manual_conversion": has_manual,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(value: object) -> float | None:
    """Convert *value* to float, returning ``None`` on failure."""
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


def _normalize_single_item(
    item: dict[str, object],
    target_uom: str,
    target_currency: str,
) -> dict[str, object]:
    """Normalize a single line-item dict."""

    # --- Read original values ------------------------------------------------
    original_uom: str = str(item.get("unit") or item.get("uom") or "").strip()
    original_price = _safe_float(item.get("unit_price"))
    original_quantity = _safe_float(item.get("quantity"))
    currency_value = item.get("currency")
    original_currency = str(currency_value).strip().upper() if currency_value is not None else ""
    item_name: str = str(item.get("product_name") or item.get("item_name") or "")

    result: dict[str, object] = {
        **item,
        "item_name": item_name,
        "currency": original_currency or None,
    }
    result.pop("product_name", None)
    result.pop("uom", None)

    # --- Currency conversion -------------------------------------------------
    normalized_currency = target_currency
    currency_rate: float | None = None

    if original_price is not None:
        currency_rate = _get_currency_rate(original_currency, target_currency)

    # --- UOM conversion ------------------------------------------------------
    uom_ok, uom_factor = _get_uom_factor(original_uom, target_uom)

    requires_manual = not original_currency
    conversion_note = ""
    normalized_price: float | None = None
    normalized_quantity: float | None = original_quantity

    if not original_uom:
        requires_manual = True
        conversion_note = "Thiếu UOM; không thể chuẩn hóa"
    elif not uom_ok:
        # Preserve the original price for review, but never expose it as a
        # normalized value when no deterministic conversion rule exists.
        requires_manual = True
        conversion_note = f"Không có quy tắc đổi {original_uom} sang {target_uom}; cần xử lý thủ công"
    else:
        # Valid UOM conversion
        if uom_factor == 1.0:
            conversion_note = f"Cùng đơn vị ({original_uom})"
        else:
            conversion_note = f"1 {original_uom} = {uom_factor} {target_uom}"

        if original_price is not None:
            # Price per target unit = original price / factor
            normalized_price = original_price / uom_factor
        if original_quantity is not None:
            normalized_quantity = original_quantity * uom_factor

    # Apply currency conversion to the normalised price
    if normalized_price is not None and currency_rate is not None and currency_rate != 1.0:
        normalized_price = normalized_price * currency_rate
        conversion_note += f"; tỷ giá {original_currency}→{target_currency}: {currency_rate}"
    elif normalized_price is not None and currency_rate is None:
        requires_manual = True
        normalized_price = None
        conversion_note += f"; không có tỷ giá {original_currency}→{target_currency}"
        normalized_price = None

    normalized_surcharges, surcharge_manual = _normalize_surcharges(
        item.get("surcharges"),
        original_currency or None,
        target_currency,
    )
    requires_manual = requires_manual or surcharge_manual

    result.update(
        {
            "normalized_uom": target_uom,
            "normalized_unit_price": normalized_price,
            "normalized_quantity": normalized_quantity,
            "normalized_currency": normalized_currency,
            "surcharges": normalized_surcharges,
            "requires_manual_conversion": requires_manual,
            "conversion_note": conversion_note,
        }
    )

    return result


def _normalize_surcharges(
    value: object,
    default_currency: str | None,
    target_currency: str,
) -> tuple[list[dict[str, object]], bool]:
    """Normalize surcharge amounts without discarding descriptions or sources."""
    if not isinstance(value, list):
        return [], False

    normalized: list[dict[str, object]] = []
    requires_manual = False
    for entry in value:
        if not isinstance(entry, dict):
            continue
        surcharge = dict(entry)
        amount = _safe_float(entry.get("amount"))
        currency_value = entry.get("currency") or default_currency
        currency = str(currency_value).upper() if currency_value is not None else None
        rate = _get_currency_rate(currency, target_currency)
        normalized_amount = amount * rate if amount is not None and rate is not None else None
        surcharge_manual = amount is not None and rate is None
        surcharge.update(
            {
                "currency": currency,
                "normalized_amount": normalized_amount,
                "normalized_currency": target_currency,
                "requires_manual_conversion": surcharge_manual,
            }
        )
        normalized.append(surcharge)
        requires_manual = requires_manual or surcharge_manual
    return normalized, requires_manual


def _get_uom_factor(source_uom: str, target_uom: str) -> tuple[bool, float]:
    """Return ``(success, factor)`` to convert *source_uom* → *target_uom*.

    ``factor`` is defined such that ``1 source_uom = factor target_uom``.
    If either UOM is not in the conversion table, returns ``(False, 0.0)``.
    """

    src_key = source_uom.lower()
    tgt_key = target_uom.lower()

    # Same unit (case-insensitive) — trivial
    if src_key == tgt_key:
        return True, 1.0

    src_entry = UOM_CONVERSION_TABLE.get(src_key)
    tgt_entry = UOM_CONVERSION_TABLE.get(tgt_key)

    if src_entry is None or tgt_entry is None:
        return False, 0.0

    src_base, src_mult = src_entry
    tgt_base, tgt_mult = tgt_entry

    # Units must share the same base dimension (e.g. both "cái"-based)
    if src_base != tgt_base:
        return False, 0.0

    # factor: how many target units per 1 source unit
    factor = src_mult / tgt_mult
    return True, factor


def _get_currency_rate(source_currency: str | None, target_currency: str) -> float | None:
    """Return the multiplier to convert *source_currency* → *target_currency*.

    Returns ``None`` when either currency is unknown.
    """

    if source_currency is None:
        return None

    src_key = source_currency.upper().strip()
    tgt_key = target_currency.upper().strip()

    if src_key == tgt_key:
        return 1.0

    src_to_vnd = FX_RATES_TO_VND.get(src_key)
    tgt_to_vnd = FX_RATES_TO_VND.get(tgt_key)

    if src_to_vnd is None or tgt_to_vnd is None:
        return None

    return src_to_vnd / tgt_to_vnd
