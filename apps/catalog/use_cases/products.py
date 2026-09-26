from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.catalog.domain.product_rules import name_key, normalize_product_name
from apps.catalog.models import Category, Product
from apps.inventory.models import StockLevel

_LIVE_BARCODE_CONSTRAINT = "uniq_product_live_barcode"


class BarcodeExistsError(Exception):
    pass


class CategoryNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class NewProduct:
    barcode: str
    name: str
    category_id: int
    unit: str
    price: Decimal
    cost: Decimal
    stock: Decimal = Decimal("0")
    low_stock_alert: Decimal = Decimal("0")


def create_product(tenant_id: int, user_id: int, new: NewProduct) -> Product:
    """Opening stock writes the stock level (qty 0 when none is given)."""
    product = Product(
        tenant_id=tenant_id,
        barcode=new.barcode,
        name=normalize_product_name(new.name),
        name_lc=name_key(new.name),
        category=tenant_category(tenant_id, new.category_id),
        unit=new.unit,
        price=new.price,
        cost=new.cost,
        low_stock_alert=new.low_stock_alert,
    )
    with transaction.atomic():
        save_product(product)
        StockLevel.objects.create(tenant_id=tenant_id, product=product, qty=new.stock)
        _log_created(product, user_id, new.stock)
    return product


def tenant_category(tenant_id: int, category_id: int) -> Category:
    category = Category.objects.for_tenant(tenant_id).filter(id=category_id, is_active=True).first()
    if category is None:
        raise CategoryNotFoundError
    return category


def save_product(product: Product) -> None:
    try:
        with transaction.atomic():
            product.save()
    except IntegrityError as error:
        if _LIVE_BARCODE_CONSTRAINT in str(error):
            raise BarcodeExistsError from None
        raise


def product_snapshot(product: Product) -> dict:
    return {
        "barcode": product.barcode,
        "name": product.name,
        "category_id": product.category_id,
        "unit": product.unit,
        "price": str(product.price),
        "cost": str(product.cost),
        "low_stock_alert": str(product.low_stock_alert),
    }


def _log_created(product: Product, user_id: int, stock: Decimal) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=product.tenant_id,
            user_id=user_id,
            action="product_created",
            entity_type="product",
            entity_id=str(product.id),
            after={**product_snapshot(product), "stock": str(stock)},
        )
    )
