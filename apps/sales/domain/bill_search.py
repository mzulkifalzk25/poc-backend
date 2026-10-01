import re

_NON_DIGITS = re.compile(r"\D")


def bill_no_digits(raw: str) -> str:
    """`002-000743` and `002000743` both search as `002000743`; a partial
    number keeps its digits so it matches the start of the bill number."""
    return _NON_DIGITS.sub("", raw)
