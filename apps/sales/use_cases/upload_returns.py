from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.accounts.repositories.users import UserRepository, user_repository
from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.catalog.repositories.sale_prices import SalePriceRepository, sale_price_repository
from apps.core.domain.money import Money
from apps.inventory.models import StockMovement
from apps.inventory.repositories.sale_stock import SaleStockRepository, sale_stock_repository
from apps.sales.domain.bill_number import is_valid_bill_no
from apps.sales.domain.errors import BatchBusyError, ReturnIdTakenError
from apps.sales.domain.returns import (
    ReturnedQty,
    after_return,
    bill_status,
    is_paid_from_drawer,
    ordered_return_flags,
)
from apps.sales.domain.totals import TaxRule
from apps.sales.models import Return, ReturnItem
from apps.sales.repositories.returns import LockedBill, ReturnRepository, return_repository
from apps.shifts.repositories.shifts import ShiftRepository, shift_repository
from apps.tenants.repositories.settings import SettingsRepository, settings_repository

from .bill_upload import CREATED, DUPLICATE, REJECTED
from .return_planning import PlannedReturn, ReturnContext, bill_key, plan_return
from .return_upload import ReturnBatch, ReturnResult


@dataclass(frozen=True)
class ReturnRepositories:
    returns: ReturnRepository = return_repository
    prices: SalePriceRepository = sale_price_repository
    users: UserRepository = user_repository
    shifts: ShiftRepository = shift_repository
    settings: SettingsRepository = settings_repository
    stock: SaleStockRepository = sale_stock_repository


def upload_returns(
    batch: ReturnBatch, repos: ReturnRepositories | None = None
) -> list[ReturnResult]:
    """One transaction per batch, one savepoint per return. A return that
    happened is never refused: only malformed or foreign data is rejected."""
    repos = repos or ReturnRepositories()
    with transaction.atomic():
        if not repos.returns.try_lock_counter(batch.counter_id):
            raise BatchBusyError
        ctx = _load_context(batch, repos)
        results, created = [], []
        for upload in batch.returns:
            plan = plan_return(upload, ctx)
            result = plan if isinstance(plan, ReturnResult) else _store(plan, batch, ctx, repos)
            if result.status == CREATED:
                created.append(plan)
            results.append(result)
        _write_stock(batch, created, repos)
        _write_bill_statuses(batch.tenant_id, created, ctx, repos)
    return results


def _load_context(batch: ReturnBatch, repos: ReturnRepositories) -> ReturnContext:
    tenant_id = batch.tenant_id
    uploads = batch.returns
    product_ids = [line.product_id for upload in uploads for line in upload.lines]
    settings = repos.settings.for_tenant(tenant_id)
    earliest = min((upload.returned_at for upload in uploads), default=batch.received_at)
    bill_nos = {bill_key(upload.original_bill_no) for upload in uploads}
    return ReturnContext(
        tax=TaxRule(settings.tax_rate, settings.prices_include_tax),
        received_at=batch.received_at,
        token_cashier_id=batch.cashier_id,
        products=repos.prices.products_by_id(tenant_id, product_ids),
        price_changes=repos.prices.changes_after(tenant_id, product_ids, earliest),
        user_ids=repos.users.ids_in_tenant(
            tenant_id, [upload.cashier_id for upload in uploads if upload.cashier_id]
        ),
        shift_cashiers=repos.shifts.cashiers_of(tenant_id, [upload.shift_id for upload in uploads]),
        stored_flags=repos.returns.stored_flags(tenant_id, [upload.id for upload in uploads]),
        bills=repos.returns.lock_bills(tenant_id, {no for no in bill_nos if is_valid_bill_no(no)}),
        seen_ids=set(),
    )


def _store(
    plan: PlannedReturn, batch: ReturnBatch, ctx: ReturnContext, repos: ReturnRepositories
) -> ReturnResult:
    upload = plan.upload
    flags = ordered_return_flags(plan.flags)
    record = _record(plan, flags, batch)
    try:
        repos.returns.add(record, _items(plan, record))
    except ReturnIdTakenError:
        stored = repos.returns.stored_flags(batch.tenant_id, [upload.id])
        if upload.id in stored:
            return ReturnResult(str(upload.id), DUPLICATE, stored[upload.id])
        return ReturnResult(str(upload.id), REJECTED, [], ["id: This return id is used."])
    if plan.bill is not None:
        _take_back(plan, ctx)
    _log_return(plan, record, ctx)
    return ReturnResult(str(upload.id), CREATED, flags)


def _take_back(plan: PlannedReturn, ctx: ReturnContext) -> None:
    """The next return in this batch sees what this one took back and paid."""
    bill = plan.bill
    taken = [ReturnedQty(line.product_id, line.qty) for line in plan.refund.lines]
    after = after_return(bill.found, taken, Money(plan.upload.refund_amount))
    ctx.bills[bill.bill_no] = LockedBill(bill.id, bill.bill_no, after)


def _record(plan: PlannedReturn, flags: list[str], batch: ReturnBatch) -> Return:
    upload = plan.upload
    return Return(
        id=upload.id,
        tenant_id=batch.tenant_id,
        counter_id=batch.counter_id,
        shift_id=upload.shift_id,
        cashier_id=plan.cashier_id,
        original_bill_no=upload.original_bill_no,
        original_bill_id=plan.bill.id if plan.bill else None,
        reason=upload.reason,
        restock=upload.restock,
        refund_method=upload.refund_method,
        paid_from_drawer=is_paid_from_drawer(upload.refund_method),
        refund_total=upload.refund_amount,
        returned_at=upload.returned_at,
        received_at=batch.received_at,
        flags=flags,
        device_id=batch.device_id,
    )


def _items(plan: PlannedReturn, record: Return) -> list[ReturnItem]:
    return [
        ReturnItem(
            tenant_id=record.tenant_id,
            return_record=record,
            product_id=line.product_id,
            bill_item_id=line.bill_item_id,
            qty=line.qty,
            price_source=line.price_source,
            unit_price=line.unit_price,
            refund_amount=line.refund_amount.amount,
            tax_refund=line.tax_refund.amount,
            cost_snapshot=line.cost_snapshot,
        )
        for line in plan.refund.lines
    ]


def _write_stock(
    batch: ReturnBatch, created: list[PlannedReturn], repos: ReturnRepositories
) -> None:
    restocked = [plan for plan in created if plan.upload.restock]
    deltas: dict[int, Decimal] = defaultdict(Decimal)
    movements = []
    for plan in restocked:
        for line in plan.refund.lines:
            deltas[line.product_id] += line.qty
            movements.append(_return_movement(plan, line.product_id, line.qty, batch.tenant_id))
    if movements:
        repos.stock.lock_levels(batch.tenant_id, deltas)
        repos.stock.record(batch.tenant_id, movements, deltas, batch.received_at)


def _return_movement(
    plan: PlannedReturn, product_id: int, qty: Decimal, tenant_id: int
) -> StockMovement:
    return StockMovement(
        tenant_id=tenant_id,
        product_id=product_id,
        type=StockMovement.Type.RETURN,
        qty_delta=qty,
        ref_type="return",
        ref_id=str(plan.upload.id),
        user_id=plan.cashier_id,
        occurred_at=plan.upload.returned_at,
    )


def _write_bill_statuses(
    tenant_id: int, created: list[PlannedReturn], ctx: ReturnContext, repos: ReturnRepositories
) -> None:
    touched: dict[UUID, str] = {plan.bill.id: plan.bill.bill_no for plan in created if plan.bill}
    for bill_id in sorted(touched):
        found = ctx.bills[touched[bill_id]].found
        repos.returns.set_bill_status(tenant_id, bill_id, bill_status(found))


def _log_return(plan: PlannedReturn, record: Return, ctx: ReturnContext) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=record.tenant_id,
            user_id=record.cashier_id,
            action="return_processed",
            entity_type="return",
            entity_id=str(record.id),
            device_id=record.device_id,
            detail={
                "counter_id": record.counter_id,
                "original_bill_no": record.original_bill_no,
                "reason": record.reason,
                "restock": record.restock,
                "refund_method": record.refund_method,
                "amount": f"{record.refund_total:.2f}",
                "items": [
                    {
                        "product_id": line.product_id,
                        "name": ctx.products[line.product_id].name,
                        "qty": f"{line.qty:.3f}",
                    }
                    for line in plan.refund.lines
                ],
                "flags": record.flags,
            },
            occurred_at=record.returned_at,
        )
    )
