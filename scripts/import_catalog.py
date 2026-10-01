"""Loads categories, products, prices and opening stock from the Pakistan mart
CSV into ONE tenant. Safe to run twice: existing categories are reused and a
barcode that is already a live product is skipped.

    python scripts/import_catalog.py --tenant-id 2
"""

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "pakistan_mart_poc_products.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()
    from apps.accounts.models import User
    from apps.catalog.domain.errors import BarcodeExistsError
    from apps.catalog.models import Category
    from apps.catalog.use_cases.categories import create_category
    from apps.catalog.use_cases.products import NewProduct, create_product
    from apps.tenants.models import Tenant
    from scripts.seed.catalog_import import category_names, read_rows, tint_for

    tenant = Tenant.objects.get(id=args.tenant_id)
    owner = User.objects.for_tenant(tenant.id).filter(role="owner").order_by("id").first()
    if owner is None:
        sys.exit(f"{tenant.name} has no owner account yet.")
    rows = read_rows(args.csv)
    categories = {}
    for position, name in enumerate(category_names(rows)):
        existing = Category.objects.for_tenant(tenant.id).filter(name__iexact=name).first()
        categories[name] = existing or create_category(tenant.id, name, tint_for(position))
    added = skipped = 0
    for row in rows:
        try:
            create_product(
                tenant.id,
                owner.id,
                NewProduct(
                    barcode=row.barcode,
                    name=row.name,
                    category_id=categories[row.category].id,
                    unit=row.unit,
                    price=row.price,
                    cost=row.cost,
                    stock=Decimal(row.stock),
                    low_stock_alert=row.low_stock_alert,
                ),
            )
            added += 1
        except BarcodeExistsError:
            skipped += 1
    summary = f"{len(categories)} categories, {added} products added, {skipped} skipped."
    print(f"{tenant.name} (id {tenant.id}): {summary}")


if __name__ == "__main__":
    main()
