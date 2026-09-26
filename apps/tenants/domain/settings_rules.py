from decimal import Decimal

MIN_TAX_RATE = Decimal("0")
MAX_TAX_RATE = Decimal("100")


def is_valid_tax_rate(rate: Decimal) -> bool:
    """`tax_rate` is a percent: `17.00` means 17%, not a fraction."""
    return MIN_TAX_RATE <= rate <= MAX_TAX_RATE


RECEIPT_PAPER_WIDTHS_MM = (58, 80)


def is_valid_receipt_paper_width(width_mm: int) -> bool:
    return width_mm in RECEIPT_PAPER_WIDTHS_MM
