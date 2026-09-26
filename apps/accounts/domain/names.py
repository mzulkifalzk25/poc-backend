import re

_WHITESPACE = re.compile(r"\s+")


def normalize_full_name(raw: str) -> str:
    """Trim and collapse inner whitespace, matching how names are compared."""
    return _WHITESPACE.sub(" ", raw.strip())


def initials(full_name: str) -> str:
    """`Zainab Khan` → `ZK`; a single word gives one letter."""
    words = normalize_full_name(full_name).split(" ")
    if not words[0]:
        return ""
    letters = words[0][0] + (words[-1][0] if len(words) > 1 else "")
    return letters.upper()
