from decimal import Decimal

from apps.catalog.domain.product_rules import stock_status
from apps.catalog.models import Product

QTY_PLACES = Decimal("0.001")


def present_product(product: Product, qty: Decimal | None, include_cost: bool) -> dict:
    """List row. `cost` is left out entirely for cashiers."""
    stock = (qty or Decimal("0")).quantize(QTY_PLACES)
    row = {
        "id": product.id,
        "barcode": product.barcode,
        "name": product.name,
        "category": {
            "id": product.category_id,
            "name": product.category.name,
            "tint": product.category.tint,
        },
        "unit": product.unit,
        "price": str(product.price),
        "stock": str(stock),
        "status": stock_status(stock, product.low_stock_alert, product.is_archived),
    }
    if include_cost:
        row["cost"] = str(product.cost)
    return row


def present_product_detail(product: Product, qty: Decimal | None) -> dict:
    return {
        **present_product(product, qty, include_cost=True),
        "low_stock_alert": str(product.low_stock_alert),
        "is_archived": product.is_archived,
        "archived_at": product.archived_at.isoformat().replace("+00:00", "Z")
        if product.archived_at
        else None,
    }
