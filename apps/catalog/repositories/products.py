from decimal import Decimal

from django.db.models import F, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from apps.accounts.models import User
from apps.catalog.models import PriceHistory, Product
from apps.inventory.models import StockLevel


def products_with_stock(tenant_id: int) -> QuerySet[Product]:
    """Products with their category and stock `qty` in one query."""
    levels = StockLevel.objects.for_tenant(tenant_id).filter(product=OuterRef("pk"))
    return (
        Product.objects.for_tenant(tenant_id)
        .select_related("category")
        .annotate(qty=Subquery(levels.values("qty")[:1]))
    )


def filter_products(queryset: QuerySet[Product], filters: dict) -> QuerySet[Product]:
    """`stock=out` includes negative stock; `low` is above zero and at or under
    the alert level. Archived products show only with `archived=true`."""
    queryset = queryset.filter(is_archived=filters.get("archived", False))
    search = filters.get("search", "").strip()
    if search:
        by_name_or_barcode = Q(name_lc__contains=search.lower()) | Q(barcode__startswith=search)
        queryset = queryset.filter(by_name_or_barcode)
    if filters.get("category"):
        queryset = queryset.filter(category_id=filters["category"])
    return _filter_stock(queryset, filters.get("stock", "all"))


def _filter_stock(queryset: QuerySet[Product], stock: str) -> QuerySet[Product]:
    queryset = queryset.annotate(stock_qty=Coalesce("qty", Value(Decimal("0"))))
    if stock == "out":
        return queryset.filter(stock_qty__lte=0)
    if stock == "low":
        return queryset.filter(
            stock_qty__gt=0, low_stock_alert__gt=0, stock_qty__lte=F("low_stock_alert")
        )
    return queryset


def price_history_rows(product: Product) -> list[tuple[PriceHistory, str | None]]:
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
