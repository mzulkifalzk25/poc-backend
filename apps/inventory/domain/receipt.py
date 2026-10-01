from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class ReceiptLineFigures:
    qty: Decimal
    unit_cost: Decimal
    prev_cost: Decimal


def line_total(line: ReceiptLineFigures) -> Decimal:
    return (line.qty * line.unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def receipt_total(lines: list[ReceiptLineFigures]) -> Decimal:
    return sum((line_total(line) for line in lines), Decimal("0.00"))


def costs_more(line: ReceiptLineFigures) -> bool:
    """A cost above the last one the store paid (a first delivery, with no
    earlier cost, is never a warning)."""
    return line.prev_cost > 0 and line.unit_cost > line.prev_cost
