from decimal import Decimal

from scripts.import_catalog import DEFAULT_CSV
from scripts.seed.catalog_import import (
    TINTS,
    app_unit,
    category_names,
    cost_for,
    read_rows,
    tint_for,
)


def test_units_map_to_the_four_the_app_has():
    assert [app_unit(u) for u in ("kg", "L", "Pack", "g", "ml", "pc", "unit", "mAh")] == [
        "kg",
        "litre",
        "pack",
        "pcs",
        "pcs",
        "pcs",
        "pcs",
        "pcs",
    ]


def test_cost_is_80_to_90_percent_of_price_and_repeatable():
    price = Decimal("1000")
    costs = {cost_for(price, n) for n in range(40)}

    assert all(Decimal("800") <= cost <= Decimal("900") for cost in costs)
    assert cost_for(price, 3) == cost_for(price, 3)


def test_tints_cycle_through_the_design_keys():
    assert [tint_for(n) for n in range(8)] == [*TINTS, TINTS[0]]


def test_the_file_reads_into_priced_stocked_rows():
    rows = read_rows(DEFAULT_CSV)

    assert len(rows) == 379 and len(category_names(rows)) == 26
    assert len({row.barcode for row in rows}) == 379
    assert all(row.unit in ("pcs", "kg", "litre", "pack") for row in rows)
    assert all(row.cost < row.price and row.stock > 0 for row in rows)
