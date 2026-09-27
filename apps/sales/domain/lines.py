from dataclasses import dataclass, replace
from decimal import Decimal


@dataclass(frozen=True)
class SaleLine:
    line_no: int
    product_id: int
    barcode: str
    name: str
    qty: Decimal
    unit_price: Decimal


def merge_lines(lines: list[SaleLine]) -> list[SaleLine]:
    """One row per product. A repeated product adds its quantity to the first
    row for that product, which keeps its line number, name and price."""
    merged: dict[int, SaleLine] = {}
    for line in lines:
        first = merged.get(line.product_id)
        merged[line.product_id] = (
            line if first is None else replace(first, qty=first.qty + line.qty)
        )
    return list(merged.values())
