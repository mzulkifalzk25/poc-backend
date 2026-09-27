from datetime import datetime
from decimal import Decimal
from typing import Protocol

from django.db import IntegrityError, transaction
from django.db.models import F, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from apps.accounts.models import User
from apps.catalog.domain.errors import BarcodeExistsError
from apps.catalog.models import Category, PriceHistory, Product
from apps.inventory.models import StockLevel

_LIVE_BARCODE_CONSTRAINT = "uniq_product_live_barcode"


class ProductRepository(Protocol):
    def list_rows(self, tenant_id: int, filters: dict) -> QuerySet[Product]: ...

    def with_stock(self, tenant_id: int, product_id: int) -> Product | None: ...

    def live_by_barcode(self, tenant_id: int, barcode: str) -> Product | None: ...

    def save(self, product: Product) -> None: ...

    def save_unique(self, product: Product) -> None: ...

    def any_in_category(self, category: Category) -> bool: ...

    def move_category(self, category: Category, target: Category, now: datetime) -> int: ...


class DjangoProductRepository:
    def list_rows(self, tenant_id: int, filters: dict) -> QuerySet[Product]:
        """The admin list, sorted by name. `stock=out` includes negative stock;
        `low` is above zero and at or under the alert level. Archived products
        show only with `archived=true`."""
        products = _with_stock(tenant_id).filter(is_archived=filters.get("archived", False))
        search = filters.get("search", "").strip()
        if search:
            by_name_or_barcode = Q(name_lc__contains=search.lower()) | Q(barcode__startswith=search)
            products = products.filter(by_name_or_barcode)
        if filters.get("category"):
            products = products.filter(category_id=filters["category"])
        return _filter_stock(products, filters.get("stock", "all")).order_by("name_lc", "id")

    def with_stock(self, tenant_id: int, product_id: int) -> Product | None:
        return _with_stock(tenant_id).filter(id=product_id).first()

    def live_by_barcode(self, tenant_id: int, barcode: str) -> Product | None:
        return _with_stock(tenant_id).filter(barcode=barcode, is_archived=False).first()

    def save(self, product: Product) -> None:
        product.save()

    def save_unique(self, product: Product) -> None:
        try:
            with transaction.atomic():
                product.save()
        except IntegrityError as error:
            if _LIVE_BARCODE_CONSTRAINT in str(error):
                raise BarcodeExistsError from None
            raise

    def any_in_category(self, category: Category) -> bool:
        """Archived products still point at their category, so they count too."""
        return Product.objects.for_tenant(category.tenant_id).filter(category=category).exists()

    def move_category(self, category: Category, target: Category, now: datetime) -> int:
        """Live and archived products. `updated_at` is set explicitly (a bulk
        update skips auto_now) so counters pick the change up in sync."""
        products = Product.objects.for_tenant(category.tenant_id).filter(category=category)
        return products.update(category=target, updated_at=now)


def _with_stock(tenant_id: int) -> QuerySet[Product]:
    """Products with their category and stock `qty` in one query."""
    levels = StockLevel.objects.for_tenant(tenant_id).filter(product=OuterRef("pk"))
    return (
        Product.objects.for_tenant(tenant_id)
        .select_related("category")
        .annotate(qty=Subquery(levels.values("qty")[:1]))
    )


def _filter_stock(queryset: QuerySet[Product], stock: str) -> QuerySet[Product]:
    queryset = queryset.annotate(stock_qty=Coalesce("qty", Value(Decimal("0"))))
    if stock == "out":
        return queryset.filter(stock_qty__lte=0)
    if stock == "low":
        return queryset.filter(
            stock_qty__gt=0, low_stock_alert__gt=0, stock_qty__lte=F("low_stock_alert")
        )
    return queryset


class PriceHistoryRepository(Protocol):
    def add(
        self, product: Product, old_price: Decimal, user_id: int, now: datetime
    ) -> PriceHistory: ...

    def rows_with_names(self, product: Product) -> list[tuple[PriceHistory, str | None]]: ...


class DjangoPriceHistoryRepository:
    def add(
        self, product: Product, old_price: Decimal, user_id: int, now: datetime
    ) -> PriceHistory:
        return PriceHistory.objects.create(
            tenant_id=product.tenant_id,
            product=product,
            old_price=old_price,
            new_price=product.price,
            changed_by=user_id,
            source="edit",
            changed_at=now,
        )

    def rows_with_names(self, product: Product) -> list[tuple[PriceHistory, str | None]]:
        """Newest first, each with the name of the user who changed the price."""
        rows = list(
            PriceHistory.objects.for_tenant(product.tenant_id)
            .filter(product=product)
            .order_by("-changed_at", "-id")
        )
        names = dict(
            User.objects.for_tenant(product.tenant_id)
            .filter(id__in={row.changed_by for row in rows})
            .values_list("id", "full_name")
        )
        return [(row, names.get(row.changed_by)) for row in rows]


product_repository = DjangoProductRepository()
price_history_repository = DjangoPriceHistoryRepository()
