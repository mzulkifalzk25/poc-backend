from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.catalog.domain.product_rules import name_key, normalize_product_name
from apps.catalog.models import Category, PriceHistory, Product
from apps.catalog.repositories.categories import CategoryRepository, category_repository
from apps.catalog.repositories.products import (
    PriceHistoryRepository,
    ProductRepository,
    price_history_repository,
    product_repository,
)
from apps.inventory.repositories.stock_levels import StockLevelRepository, stock_level_repository


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


def product_rows(
    tenant_id: int, filters: dict, products: ProductRepository = product_repository
) -> QuerySet[Product]:
    return products.list_rows(tenant_id, filters)


def find_product(
    tenant_id: int, product_id: int, products: ProductRepository = product_repository
) -> Product | None:
    """With its stock `qty`, archived or not."""
    return products.with_stock(tenant_id, product_id)


def live_product_by_barcode(
    tenant_id: int, barcode: str, products: ProductRepository = product_repository
) -> Product | None:
    return products.live_by_barcode(tenant_id, barcode.strip())


def price_history(
    product: Product, prices: PriceHistoryRepository = price_history_repository
) -> list[tuple[PriceHistory, str | None]]:
    return prices.rows_with_names(product)


def create_product(
    tenant_id: int,
    user_id: int,
    new: NewProduct,
    products: ProductRepository = product_repository,
    categories: CategoryRepository = category_repository,
    stock: StockLevelRepository = stock_level_repository,
) -> Product:
    """Opening stock writes the stock level (qty 0 when none is given)."""
    product = Product(
        tenant_id=tenant_id,
        barcode=new.barcode,
        name=normalize_product_name(new.name),
        name_lc=name_key(new.name),
        category=_tenant_category(categories, tenant_id, new.category_id),
        unit=new.unit,
        price=new.price,
        cost=new.cost,
        low_stock_alert=new.low_stock_alert,
    )
    with transaction.atomic():
        products.save_unique(product)
        stock.add(product, new.stock)
        _log_created(product, user_id, new.stock)
    return product


def _tenant_category(categories: CategoryRepository, tenant_id: int, category_id: int) -> Category:
    category = categories.active_in_tenant(tenant_id, category_id)
    if category is None:
        raise CategoryNotFoundError
    return category


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


UPDATABLE_FIELDS = ("barcode", "name", "unit", "price", "cost", "low_stock_alert")


def update_product(
    product: Product,
    user_id: int,
    changes: dict,
    now: datetime,
    products: ProductRepository = product_repository,
    categories: CategoryRepository = category_repository,
    prices: PriceHistoryRepository = price_history_repository,
) -> Product:
    """A price change writes price_history and the activity log in the same
    transaction. Stock is not edited here (stock adjust, Step B7)."""
    old_price = product.price
    for name in UPDATABLE_FIELDS:
        if name in changes:
            setattr(product, name, changes[name])
    product.name_lc = name_key(product.name)
    if "category_id" in changes:
        product.category = _tenant_category(categories, product.tenant_id, changes["category_id"])
    with transaction.atomic():
        products.save_unique(product)
        if product.price != old_price:
            prices.add(product, old_price, user_id, now)
            _log_price_change(product, old_price, user_id, now)
    return product


def _log_price_change(product: Product, old_price: Decimal, user_id: int, now: datetime) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=product.tenant_id,
            user_id=user_id,
            action="price_changed",
            entity_type="product",
            entity_id=str(product.id),
            before={"price": str(old_price)},
            after={"price": str(product.price)},
            occurred_at=now,
        )
    )


def archive_product(
    product: Product,
    user_id: int,
    now: datetime,
    products: ProductRepository = product_repository,
) -> Product:
    """Deleting a product archives it; archiving twice changes nothing."""
    if product.is_archived:
        return product
    product.is_archived = True
    product.archived_at = now
    product.archived_by = user_id
    with transaction.atomic():
        products.save(product)
        _log_state(product, user_id, "product_archived", now)
    return product


def restore_product(
    product: Product,
    user_id: int,
    now: datetime,
    products: ProductRepository = product_repository,
) -> Product:
    """Refused while another live product uses the barcode."""
    if not product.is_archived:
        return product
    product.is_archived = False
    product.archived_at = None
    product.archived_by = None
    with transaction.atomic():
        products.save_unique(product)
        _log_state(product, user_id, "product_restored", now)
    return product


def _log_state(product: Product, user_id: int, action: str, now: datetime) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=product.tenant_id,
            user_id=user_id,
            action=action,
            entity_type="product",
            entity_id=str(product.id),
            detail={"barcode": product.barcode, "name": product.name},
            occurred_at=now,
        )
    )
