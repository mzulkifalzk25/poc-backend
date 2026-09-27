"""The small POC data set (step prompt section 8 and DESIGN_SPEC sample data)."""

from dataclasses import dataclass
from decimal import Decimal

from scripts.seed.barcodes import sample_barcode

TENANT_SLUG = "fresh-basket-mart"
STORE_NAME = "Fresh Basket Mart"
TIMEZONE = "Asia/Karachi"
OWNER_NAME = "Sana Ahmed"
OWNER_USERNAME = "sana"


@dataclass(frozen=True)
class SampleCounter:
    code: str
    name: str
    activated: bool


@dataclass(frozen=True)
class SampleCashier:
    full_name: str
    counter_code: str | None
    is_active: bool = True


@dataclass(frozen=True)
class SampleCategory:
    name: str
    tint: str


@dataclass(frozen=True)
class SampleProduct:
    barcode: str
    name: str
    category: str
    unit: str
    price: Decimal
    cost: Decimal
    stock: Decimal
    low_stock_alert: Decimal


COUNTERS = (
    SampleCounter("001", "Counter 1", activated=True),
    SampleCounter("002", "Counter 2", activated=True),
    SampleCounter("003", "Counter 3", activated=False),
)

CASHIERS = (
    SampleCashier("Zainab Khan", "002"),
    SampleCashier("Bilal Raza", "001"),
    SampleCashier("Hina Malik", "003"),
    SampleCashier("Usman Tariq", None, is_active=False),
)

CATEGORIES = (
    SampleCategory("Grocery", "green"),
    SampleCategory("Dairy & eggs", "blue"),
    SampleCategory("Beverages", "orange"),
    SampleCategory("Snacks", "pink"),
    SampleCategory("Personal care", "purple"),
    SampleCategory("Household", "teal"),
    SampleCategory("Bakery", "yellow"),
)

# (name, category, unit, price, cost, stock, low-stock alert); Fresh Milk and
# Eggs are low, Bread Loaf is out of stock.
_PRODUCT_ROWS = (
    ("Basmati Rice 5kg", "Grocery", "pcs", "1650", "1410", "45", "10"),
    ("Cooking Oil 1L", "Grocery", "litre", "620", "540", "60", "12"),
    ("Tea Bags 100pk", "Beverages", "pack", "540", "465", "38", "10"),
    ("Fresh Milk 1L", "Dairy & eggs", "litre", "290", "255", "8", "12"),
    ("Sugar 1kg", "Grocery", "kg", "180", "160", "120", "20"),
    ("Eggs (dozen)", "Dairy & eggs", "pack", "420", "360", "5", "10"),
    ("Bread Loaf", "Bakery", "pcs", "150", "125", "0", "10"),
    ("Shampoo 180ml", "Personal care", "pcs", "480", "400", "30", "8"),
    ("Detergent 1kg", "Household", "kg", "520", "440", "42", "10"),
    ("Biscuits Pack", "Snacks", "pack", "60", "50", "200", "24"),
)


def _product(sequence: int, row: tuple[str, ...]) -> SampleProduct:
    name, category, unit, price, cost, stock, alert = row
    return SampleProduct(
        barcode=sample_barcode(sequence),
        name=name,
        category=category,
        unit=unit,
        price=Decimal(price),
        cost=Decimal(cost),
        stock=Decimal(stock),
        low_stock_alert=Decimal(alert),
    )


PRODUCTS = tuple(_product(sequence, row) for sequence, row in enumerate(_PRODUCT_ROWS, start=1))
