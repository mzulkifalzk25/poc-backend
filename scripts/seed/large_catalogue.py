"""The `--large` set: 18,462 products and 40 counters in total, the long-term
target (contract section 7, HANDOFF). Same shape as the small set, which it
includes. Built from a fixed random seed, so every run gives the same data."""

import random
from decimal import Decimal
from itertools import product as all_combinations

from scripts.seed.barcodes import sample_barcode
from scripts.seed.sample_data import CATEGORIES, COUNTERS, PRODUCTS, SampleCounter, SampleProduct

LARGE_PRODUCT_COUNT = 18_462
LARGE_COUNTER_COUNT = 40
_RANDOM_SEED = 18_462
_OUT_SHARE = 0.002
_LOW_SHARE = 0.008
_MAX_STOCK = 400
_MIN_PRICE = 20

BRANDS = (
    "Shan", "Rafhan", "Nestle", "Olpers", "Tapal", "Lipton", "National", "Mitchell's",
    "Dalda", "Habib", "Peek Freans", "LU", "Sufi", "Seasons", "Kolson", "Shezan",
    "Surf", "Lifebuoy", "Dawn", "Nurpur",
)  # fmt: skip
VARIANTS = ("Classic", "Premium", "Value", "Gold", "Lite", "Family")
SIZES = (("Small", 1.0), ("Regular", 1.8), ("Large", 3.2))

# Category -> (item, unit, base price in rupees for the small size).
ITEMS = {
    "Grocery": (
        ("Rice", "pcs", 420), ("Flour", "pcs", 380), ("Lentils", "pcs", 300),
        ("Chickpeas", "pcs", 260), ("Salt", "pcs", 60), ("Spice Mix", "pack", 120),
        ("Cooking Oil", "litre", 560), ("Sugar", "kg", 170),
    ),
    "Dairy & eggs": (
        ("Milk", "litre", 260), ("Yogurt", "pcs", 180), ("Butter", "pcs", 350),
        ("Cheese", "pcs", 420), ("Cream", "pcs", 220), ("Eggs", "pack", 380),
        ("Lassi", "pcs", 120), ("Milk Powder", "pack", 640),
    ),
    "Beverages": (
        ("Tea", "pack", 480), ("Coffee", "pcs", 720), ("Juice", "pcs", 160),
        ("Cola", "pcs", 110), ("Water", "pcs", 60), ("Squash", "pcs", 340),
        ("Green Tea", "pack", 390), ("Energy Drink", "pcs", 190),
    ),
    "Snacks": (
        ("Biscuits", "pack", 60), ("Chips", "pack", 70), ("Nimko", "pack", 120),
        ("Cookies", "pack", 150), ("Wafers", "pack", 80), ("Cake Rusk", "pack", 200),
        ("Popcorn", "pack", 90), ("Chocolate", "pcs", 140),
    ),
    "Personal care": (
        ("Shampoo", "pcs", 420), ("Soap", "pcs", 110), ("Toothpaste", "pcs", 230),
        ("Face Wash", "pcs", 380), ("Lotion", "pcs", 450), ("Hair Oil", "pcs", 290),
        ("Deodorant", "pcs", 520), ("Hand Wash", "pcs", 260),
    ),
    "Household": (
        ("Detergent", "kg", 480), ("Dish Wash", "pcs", 210), ("Bleach", "pcs", 190),
        ("Floor Cleaner", "pcs", 320), ("Tissue Roll", "pack", 240), ("Garbage Bags", "pack", 180),
        ("Air Freshener", "pcs", 430), ("Glass Cleaner", "pcs", 280),
    ),
    "Bakery": (
        ("Bread", "pcs", 140), ("Bun", "pack", 90), ("Rusk", "pack", 160),
        ("Cake", "pcs", 480), ("Croissant", "pack", 220), ("Naan", "pack", 120),
        ("Muffin", "pack", 260), ("Sandwich Bread", "pcs", 180),
    ),
}  # fmt: skip


def large_counters() -> tuple[SampleCounter, ...]:
    """The small set's counters, then 004 to 040, each with a PC for the load test."""
    extra = (
        SampleCounter(f"{number:03d}", f"Counter {number}", activated=True)
        for number in range(len(COUNTERS) + 1, LARGE_COUNTER_COUNT + 1)
    )
    return (*COUNTERS, *extra)


def large_products() -> tuple[SampleProduct, ...]:
    """The 10 sample products, then generated ones spread evenly over the categories."""
    rng = random.Random(_RANDOM_SEED)
    names = {category: _shuffled_names(rng, category) for category in ITEMS}
    generated = []
    for index in range(LARGE_PRODUCT_COUNT - len(PRODUCTS)):
        category = CATEGORIES[index % len(CATEGORIES)].name
        sequence = len(PRODUCTS) + index + 1
        generated.append(_generated(rng, sequence, category, names[category].pop()))
    return (*PRODUCTS, *generated)


def _shuffled_names(rng: random.Random, category: str) -> list[tuple[str, str, float]]:
    names = [
        (f"{brand} {item} {variant} {size}", unit, base * factor)
        for brand, (item, unit, base), variant, (size, factor) in all_combinations(
            BRANDS, ITEMS[category], VARIANTS, SIZES
        )
    ]
    rng.shuffle(names)
    return names


def _generated(
    rng: random.Random, sequence: int, category: str, combo: tuple[str, str, float]
) -> SampleProduct:
    name, unit, base = combo
    price = max(_MIN_PRICE, round(base * rng.uniform(0.85, 1.15) / 5) * 5)
    alert = rng.choice((5, 10, 12, 20, 24))
    return SampleProduct(
        barcode=sample_barcode(sequence),
        name=name,
        category=category,
        unit=unit,
        price=Decimal(price),
        cost=Decimal(_cost(rng, price)),
        stock=Decimal(_stock(rng, alert)),
        low_stock_alert=Decimal(alert),
    )


def _cost(rng: random.Random, price: int) -> int:
    """A whole-rupee cost between 80 and 90 percent of the price."""
    return rng.randint(-(-price * 8 // 10), price * 9 // 10)


def _stock(rng: random.Random, alert: int) -> int:
    roll = rng.random()
    if roll < _OUT_SHARE:
        return 0
    if roll < _OUT_SHARE + _LOW_SHARE:
        return rng.randint(1, alert)
    return rng.randint(alert + 1, _MAX_STOCK)
