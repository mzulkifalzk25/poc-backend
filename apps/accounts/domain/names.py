import re

_WHITESPACE = re.compile(r"\s+")


def normalize_full_name(raw: str) -> str:
    """Trim and collapse inner whitespace, matching how names are compared."""
    return _WHITESPACE.sub(" ", raw.strip())
