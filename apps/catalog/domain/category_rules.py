import re

# Design colour keys (DESIGN_SPEC section 3: category tints).
TINTS = ("green", "blue", "orange", "pink", "purple", "teal", "yellow")

_WHITESPACE = re.compile(r"\s+")


def is_valid_tint(tint: str) -> bool:
    return tint in TINTS


def normalize_category_name(raw: str) -> str:
    """Trim and collapse inner whitespace; names are compared case-insensitively."""
    return _WHITESPACE.sub(" ", raw.strip())


def next_sort_order(current_max: int | None) -> int:
    return 1 if current_max is None else current_max + 1
