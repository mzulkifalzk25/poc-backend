from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.accounts.repositories.users import UserRepository, user_repository
from apps.catalog.repositories.sale_prices import SalePriceRepository, sale_price_repository
from apps.inventory.models import StockMovement
from apps.inventory.repositories.sale_stock import SaleStockRepository, sale_stock_repository
from apps.sales.domain.bill_number import counter_code_of, sequence_of
from apps.sales.domain.errors import BatchBusyError, BillIdTakenError
from apps.sales.domain.flags import NEGATIVE_STOCK, negative_stock_bills, ordered_flags
from apps.sales.domain.totals import TaxRule, line_total
from apps.sales.models import Bill, BillItem, Payment
from apps.sales.repositories.bills import BillRepository, bill_repository
from apps.tenants.repositories.counters import CounterRepository, counter_repository
from apps.tenants.repositories.devices import DeviceRepository, device_repository
from apps.tenants.repositories.settings import SettingsRepository, settings_repository

from .bill_planning import BatchContext, PlannedBill, plan_bill
from .bill_upload import CREATED, DUPLICATE, BillBatch, BillResult, rejected


@dataclass(frozen=True)
class BatchRepositories:
    bills: BillRepository = bill_repository
    prices: SalePriceRepository = sale_price_repository
    users: UserRepository = user_repository
    counters: CounterRepository = counter_repository
    devices: DeviceRepository = device_repository
    settings: SettingsRepository = settings_repository
    stock: SaleStockRepository = sale_stock_repository


def upload_bills(batch: BillBatch, repos: BatchRepositories | None = None) -> list[BillResult]:
    """One transaction per batch, one savepoint per bill. A sale that happened
    is never refused: only malformed or foreign data is rejected."""
    repos = repos or BatchRepositories()
    with transaction.atomic():
        if not repos.bills.try_lock_counter(batch.counter_id):
            raise BatchBusyError
        ctx = _load_context(batch, repos)
        plans = [plan_bill(upload, ctx) for upload in batch.bills]
        planned = [plan for plan in plans if isinstance(plan, PlannedBill)]
        _flag_negative_stock(batch.tenant_id, planned, repos)
        results = [_store(plan, batch, ctx, repos) for plan in plans]
        _write_stock(batch, plans, results, repos)
        _raise_sequence(batch, ctx, results, repos)
    return results


def _load_context(batch: BillBatch, repos: BatchRepositories) -> BatchContext:
    tenant_id = batch.tenant_id
    product_ids = [line.product_id for bill in batch.bills for line in bill.lines]
    settings = repos.settings.for_tenant(tenant_id)
    earliest = min((bill.sold_at for bill in batch.bills), default=batch.received_at)
    return BatchContext(
        counter_code=repos.counters.get(tenant_id, batch.counter_id).code,
        tax=TaxRule(settings.tax_rate, settings.prices_include_tax),
        received_at=batch.received_at,
        app_version=repos.devices.get(tenant_id, batch.device_id).app_version,
        products=repos.prices.products_by_id(tenant_id, product_ids),
        price_changes=repos.prices.changes_after(tenant_id, product_ids, earliest),
        user_ids=repos.users.ids_in_tenant(tenant_id, [bill.cashier_id for bill in batch.bills]),
        stored_flags=repos.bills.stored_flags(tenant_id, [bill.id for bill in batch.bills]),
        taken_bill_nos=repos.bills.taken_bill_nos(tenant_id, [b.bill_no for b in batch.bills]),
        seen_ids=set(),
    )


def _flag_negative_stock(
    tenant_id: int, planned: list[PlannedBill], repos: BatchRepositories
) -> None:
    quantities = [_quantities(plan) for plan in planned]
    levels = repos.stock.lock_levels(tenant_id, [pid for qty in quantities for pid in qty])
    for plan, negative in zip(planned, negative_stock_bills(levels, quantities), strict=True):
        if negative:
            plan.flags.add(NEGATIVE_STOCK)


def _write_stock(
    batch: BillBatch,
    plans: list[BillResult | PlannedBill],
    results: list[BillResult],
    repos: BatchRepositories,
) -> None:
    created = [
        plan
        for plan, result in zip(plans, results, strict=True)
        if isinstance(plan, PlannedBill) and result.status == CREATED
    ]
    deltas: dict[int, Decimal] = defaultdict(Decimal)
    for plan in created:
        for product_id, qty in _quantities(plan).items():
            deltas[product_id] -= qty
    movements = [move for plan in created for move in _sale_movements(plan, batch.tenant_id)]
    if movements:
        repos.stock.record(batch.tenant_id, movements, deltas, batch.received_at)


def _quantities(plan: PlannedBill) -> dict[int, Decimal]:
    return {line.product_id: line.qty for line in plan.lines}


def _sale_movements(plan: PlannedBill, tenant_id: int) -> list[StockMovement]:
    upload = plan.upload
    return [
        StockMovement(
            tenant_id=tenant_id,
            product_id=line.product_id,
            type=StockMovement.Type.SALE,
            qty_delta=-line.qty,
            ref_type="bill",
            ref_id=str(upload.id),
            user_id=upload.cashier_id,
            occurred_at=upload.sold_at,
        )
        for line in plan.lines
    ]


def _store(
    plan: BillResult | PlannedBill, batch: BillBatch, ctx: BatchContext, repos: BatchRepositories
) -> BillResult:
    if isinstance(plan, BillResult):
        return plan
    upload = plan.upload
    flags = ordered_flags(plan.flags)
    try:
        repos.bills.add(*_records(plan, flags, batch, ctx))
    except BillIdTakenError:
        stored = repos.bills.stored_flags(batch.tenant_id, [upload.id])
        if upload.id in stored:
            return BillResult(str(upload.id), DUPLICATE, upload.bill_no, stored[upload.id])
        return rejected(str(upload.id), upload.bill_no, ["id: This bill or payment id is used."])
    return BillResult(str(upload.id), CREATED, upload.bill_no, flags)


def _raise_sequence(
    batch: BillBatch, ctx: BatchContext, results: list[BillResult], repos: BatchRepositories
) -> None:
    sequences = [
        sequence_of(result.bill_no)
        for result in results
        if result.status == CREATED and counter_code_of(result.bill_no) == ctx.counter_code
    ]
    if sequences:
        repos.counters.raise_bill_seq(batch.tenant_id, batch.counter_id, max(sequences))


def _records(
    plan: PlannedBill, flags: list[str], batch: BillBatch, ctx: BatchContext
) -> tuple[Bill, list[BillItem], Payment]:
    upload, sent = plan.upload, plan.upload.totals
    bill = Bill(
        id=upload.id,
        tenant_id=batch.tenant_id,
        counter_id=batch.counter_id,
        shift_id=upload.shift_id,
        cashier_id=upload.cashier_id,
        bill_no=upload.bill_no,
        sold_at=upload.sold_at,
        received_at=batch.received_at,
        item_count=sent.item_count,
        subtotal=sent.subtotal,
        tax_amount=sent.tax,
        rounding=sent.rounding,
        total=sent.total,
        flags=flags,
        device_id=batch.device_id,
        app_version=ctx.app_version,
    )
    return bill, _items(plan, bill, ctx), _payment(plan, bill)


def _items(plan: PlannedBill, bill: Bill, ctx: BatchContext) -> list[BillItem]:
    return [
        BillItem(
            tenant_id=bill.tenant_id,
            bill=bill,
            line_no=line.line_no,
            product_id=line.product_id,
            name_snapshot=line.name,
            barcode_snapshot=line.barcode,
            qty=line.qty,
            unit_price=line.unit_price,
            cost_snapshot=ctx.products[line.product_id].cost,
            line_total=line_total(line).amount,
            sold_at=bill.sold_at,
        )
        for line in plan.lines
    ]


def _payment(plan: PlannedBill, bill: Bill) -> Payment:
    payment = plan.upload.payment
    return Payment(
        id=payment.id,
        tenant_id=bill.tenant_id,
        bill=bill,
        method=payment.method,
        amount=payment.amount,
        tendered=payment.tendered,
        change_given=payment.change_given,
        reference=payment.reference,
    )
