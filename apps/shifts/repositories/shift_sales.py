from typing import Protocol
from uuid import UUID

from django.db.models import Count, Q, Sum

from apps.core.domain.money import Money
from apps.sales.models import Bill, Payment, Return
from apps.shifts.domain.drawer import ShiftSales


class ShiftSalesRepository(Protocol):
    def sales_of(self, tenant_id: int, shift_id: UUID) -> ShiftSales: ...


class DjangoShiftSalesRepository:
    def sales_of(self, tenant_id: int, shift_id: UUID) -> ShiftSales:
        """Bills and returns uploaded so far for the shift. Cash counts the
        amount paid, not the amount tendered; only cash refunds leave the drawer."""
        bills = Bill.objects.for_tenant(tenant_id).filter(shift_id=shift_id)
        totals = bills.aggregate(count=Count("id"), total=Sum("total"))
        payments = (
            Payment.objects.for_tenant(tenant_id)
            .filter(bill__shift_id=shift_id)
            .values_list("method")
            .annotate(amount=Sum("amount"))
        )
        by_method = {method: Money(amount) for method, amount in payments}
        refunds = _refunds(tenant_id, shift_id)
        zero = Money.zero()
        return ShiftSales(
            bills=totals["count"],
            total_sales=Money(totals["total"] or 0),
            cash=by_method.get(Payment.Method.CASH, zero),
            card=by_method.get(Payment.Method.CARD, zero),
            wallet=by_method.get(Payment.Method.WALLET, zero),
            refund_count=refunds["count"],
            refund_amount=Money(refunds["total"] or 0),
            cash_refunds=Money(refunds["cash"] or 0),
        )


def _refunds(tenant_id: int, shift_id: UUID) -> dict:
    return (
        Return.objects.for_tenant(tenant_id)
        .filter(shift_id=shift_id)
        .aggregate(
            count=Count("id"),
            total=Sum("refund_total"),
            cash=Sum("refund_total", filter=Q(paid_from_drawer=True)),
        )
    )


shift_sales_repository = DjangoShiftSalesRepository()
