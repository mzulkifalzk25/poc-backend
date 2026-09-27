PREFIX = "896"
_BODY_LENGTH = 12


def ean13_check_digit(body: str) -> str:
    """Digits in odd positions weigh 1, even positions weigh 3."""
    if len(body) != _BODY_LENGTH or not body.isascii() or not body.isdigit():
        raise ValueError("An EAN-13 body is 12 ASCII digits.")
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(body))
    return str((10 - total % 10) % 10)


def sample_barcode(sequence: int) -> str:
    """`896` + a 9-digit sequence + the check digit: unique per sequence."""
    body = f"{PREFIX}{sequence:09d}"
    return body + ean13_check_digit(body)


def is_valid_ean13(barcode: str) -> bool:
    if len(barcode) != _BODY_LENGTH + 1 or not barcode.isascii() or not barcode.isdigit():
        return False
    return ean13_check_digit(barcode[:-1]) == barcode[-1]
