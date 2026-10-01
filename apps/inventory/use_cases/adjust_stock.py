from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import transaction

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.inventory.domain.adjustment import adjustment_delta, movement_type
from apps.inventory.models import StockMovement
from apps.inventory.repositories.sale_stock import sale_stock_repository
from apps.inventory.repositories.stock_admin import stock_admin_repository


class ProductNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Adjustment:
    product_id: int
    mode: str
    qty: Decimal
    reason: str
    note: str = ""
    key: str = ""


@dataclass(frozen=True)
class AdjustResult:
    before: Decimal
    after: Decimal


def adjust_stock(tenant_id: int, user_id: int, new: Adjustment, now: datetime) -> AdjustResult:
    """One change with a reason. The same Idempotency-Key never applies twice:
    a retry gets the original change back."""
    with transaction.atomic():
        product = stock_admin_repository.product(tenant_id, new.product_id)
        if product is None:
            raise ProductNotFoundError
        levels = sale_stock_repository.lock_levels(tenant_id, [product.id])
        before = levels[product.id]
        if new.key:
            earlier = stock_admin_repository.replayed_adjustment(tenant_id, product.id, new.key)
            if earlier:
                after = stock_admin_repository.level(tenant_id, product.id)
                return AdjustResult(before=after - earlier.qty_delta, after=after)
        delta = adjustment_delta(new.mode, new.qty, before)
        movement = StockMovement(
            tenant_id=tenant_id,
            product=product,
            type=movement_type(new.mode),
            qty_delta=delta,
            ref_type="adjust" if new.key else "",
            ref_id=new.key,
            reason=new.reason,
            note=new.note,
            user_id=user_id,
            occurred_at=now,
        )
        sale_stock_repository.record(tenant_id, [movement], {product.id: delta}, now)
        record_activity(
            ActivityEntry(
                tenant_id=tenant_id,
                user_id=user_id,
                action="stock_adjusted",
                entity_type="product",
                entity_id=str(product.id),
                before={"qty": str(before)},
                after={"qty": str(before + delta)},
                detail={"mode": new.mode, "reason": new.reason, "note": new.note},
            )
        )
    return AdjustResult(before=before, after=before + delta)
