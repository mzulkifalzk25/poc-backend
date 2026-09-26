import re
from decimal import Decimal

UNITS = ("pcs", "kg", "litre", "pack")
BARCODE_MAX_LENGTH = 64

_WHITESPACE = re.compile(r"\s+")


def normalize_product_name(raw: str) -> str:
    return _WHITESPACE.sub(" ", raw.strip())


def name_key(name: str) -> str:
    """Lower-case search key stored in `name_lc`."""
    return normalize_product_name(name).lower()


def normalize_barcode(raw: str) -> str | None:
    """Barcodes are kept as typed or scanned, minus outer spaces. Inner
    whitespace is never part of a barcode, so it makes the value invalid."""
    code = raw.strip()
    if not code or len(code) > BARCODE_MAX_LENGTH or _WHITESPACE.search(code):
        return None
    return code


def stock_status(qty: Decimal, low_stock_alert: Decimal, is_archived: bool) -> str:
    """`archived`, `negative` (below zero, allowed and flagged), `out` (zero),
    `low` (at or under the alert level) or `in_stock`."""
    if is_archived:
        return "archived"
    if qty < 0:
        return "negative"
    if qty == 0:
        return "out"
    if low_stock_alert > 0 and qty <= low_stock_alert:
        return "low"
    return "in_stock"
