from typing import Protocol
from uuid import UUID

from django.db.models import Count, Sum

from apps.core.domain.money import Money
from apps.sales.models import Bill, Payment
from apps.shifts.domain.drawer import ShiftSales


class ShiftSalesRepository(Protocol):
    def sales_of(self, tenant_id: int, shift_id: UUID) -> ShiftSales: ...


class DjangoShiftSalesRepository:
    def sales_of(self, tenant_id: int, shift_id: UUID) -> ShiftSales:
        """Bills uploaded so far for the shift. Cash counts the amount paid,
        not the amount tendered. Refunds arrive with returns (Step B6)."""
        bills = Bill.objects.for_tenant(tenant_id).filter(shift_id=shift_id)
        totals = bills.aggregate(count=Count("id"), total=Sum("total"))
        payments = (
            Payment.objects.for_tenant(tenant_id)
            .filter(bill__shift_id=shift_id)
            .values_list("method")
            .annotate(amount=Sum("amount"))
        )
        by_method = {method: Money(amount) for method, amount in payments}
        zero = Money.zero()
        return ShiftSales(
            bills=totals["count"],
            total_sales=Money(totals["total"] or 0),
            cash=by_method.get(Payment.Method.CASH, zero),
            card=by_method.get(Payment.Method.CARD, zero),
            wallet=by_method.get(Payment.Method.WALLET, zero),
            refund_count=0,
            refund_amount=zero,
            cash_refunds=zero,
        )


shift_sales_repository = DjangoShiftSalesRepository()
