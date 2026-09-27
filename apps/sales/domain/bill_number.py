"""API bill numbers: a 3-digit counter code and a 6-digit sequence, `002000743`."""

import re

_BILL_NO = re.compile(r"[0-9]{9}")


def is_valid_bill_no(bill_no: str) -> bool:
    return bool(_BILL_NO.fullmatch(bill_no))


def counter_code_of(bill_no: str) -> str:
    return bill_no[:3]


def sequence_of(bill_no: str) -> int:
    return int(bill_no[3:])


def normalize_bill_no(text: str) -> str:
    """Accepts the printed form `002-000743` too."""
    return text.strip().replace("-", "")
