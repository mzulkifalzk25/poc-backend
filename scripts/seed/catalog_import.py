"""Reads the Pakistan mart CSV and fills what the file lacks: units mapped to
the app's four, a cost under the price, a low-stock level and a category tint.
Extra columns (brand, subcategory, ids) are ignored."""

import csv
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

TINTS = ("green", "blue", "orange", "pink", "purple", "teal", "yellow")
LOW_STOCK_ALERT = Decimal("10")
_UNITS = {"kg": "kg", "L": "litre", "Pack": "pack"}


@dataclass(frozen=True)
class CatalogRow:
    category: str
    name: str
    barcode: str
    unit: str
    price: Decimal
    cost: Decimal
    stock: Decimal
    low_stock_alert: Decimal


def app_unit(source_unit: str) -> str:
    """Weight and volume units in the file are pack sizes, so they sell as pieces."""
    return _UNITS.get(source_unit, "pcs")


def cost_for(price: Decimal, position: int) -> Decimal:
    """80 to 90 percent of the price, varied by row but the same on every run."""
    share = Decimal(80 + position * 7 % 11) / Decimal(100)
    return (price * share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def tint_for(category_position: int) -> str:
    return TINTS[category_position % len(TINTS)]


def read_rows(path: Path) -> list[CatalogRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        source = [row for row in csv.DictReader(handle) if row["is_active"] == "True"]
    return [
        CatalogRow(
            category=row["category"].strip(),
            name=row["product_name"].strip(),
            barcode=row["barcode"].strip(),
            unit=app_unit(row["unit"].strip()),
            price=Decimal(row["price_pkr"]).quantize(Decimal("0.01")),
            cost=cost_for(Decimal(row["price_pkr"]), position),
            stock=Decimal(row["stock_qty"]),
            low_stock_alert=LOW_STOCK_ALERT,
        )
        for position, row in enumerate(source)
    ]


def category_names(rows: list[CatalogRow]) -> list[str]:
    """In the order they first appear in the file."""
    return list(dict.fromkeys(row.category for row in rows))
