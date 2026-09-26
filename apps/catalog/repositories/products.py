from django.db.models import OuterRef, QuerySet, Subquery

from apps.catalog.models import Product
from apps.inventory.models import StockLevel


def products_with_stock(tenant_id: int) -> QuerySet[Product]:
    """Products with their category and stock `qty` in one query."""
    levels = StockLevel.objects.for_tenant(tenant_id).filter(product=OuterRef("pk"))
    return (
        Product.objects.for_tenant(tenant_id)
        .select_related("category")
        .annotate(qty=Subquery(levels.values("qty")[:1]))
    )
