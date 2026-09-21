import re

_CODE_PATTERN = re.compile(r"\d{3}")


class CounterCodeLockedError(Exception):
    pass


def is_valid_counter_code(code: str) -> bool:
    return bool(_CODE_PATTERN.fullmatch(code))


def ensure_code_can_change(current_code: str, new_code: str, last_bill_seq: int) -> None:
    """A counter's code is locked once it has billed at least once."""
    if new_code != current_code and last_bill_seq > 0:
        raise CounterCodeLockedError


def next_bill_no(last_bill_seq: int) -> int:
    return last_bill_seq + 1


def format_bill_no(code: str, sequence: int) -> str:
    return f"{code}{sequence:06d}"
