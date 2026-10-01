from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import QuerySet

from apps.audit.use_cases.record_activity import ActivityEntry, record_activity
from apps.inventory.domain.errors import (
    ProductsNotFoundError,
    ReceiptNotFoundError,
    SupplierNameExistsError,
    SupplierNotFoundError,
)
from apps.inventory.domain.receipt import ReceiptLineFigures, costs_more, receipt_total
from apps.inventory.models import StockMovement, StockReceipt, StockReceiptLine, Supplier
from apps.inventory.repositories.receipts import ReceiptRepository, receipt_repository
from apps.inventory.repositories.sale_stock import sale_stock_repository

__all__ = [
    "NewLine",
    "NewReceipt",
    "ProductsNotFoundError",
    "ReceiptNotFoundError",
    "SupplierNameExistsError",
    "SupplierNotFoundError",
    "confirm_receipt",
    "cost_increase_lines",
    "create_receipt",
    "create_supplier",
    "find_receipt",
    "receipt_history",
    "receipt_lines",
    "supplier_list",
]


@dataclass(frozen=True)
class NewLine:
    product_id: int
    qty: Decimal
    unit_cost: Decimal


@dataclass(frozen=True)
class NewReceipt:
    supplier_id: int
    invoice_no: str
    delivery_date: date
    lines: list[NewLine]


def supplier_list(tenant_id: int, repo: ReceiptRepository = receipt_repository) -> QuerySet:
    return repo.suppliers(tenant_id)


def create_supplier(
    tenant_id: int, name: str, phone: str, repo: ReceiptRepository = receipt_repository
) -> Supplier:
    return repo.add_supplier(tenant_id, name, phone)


def create_receipt(
    tenant_id: int, new: NewReceipt, repo: ReceiptRepository = receipt_repository
) -> StockReceipt:
    """A draft: nothing moves until it is confirmed."""
    supplier = repo.supplier(tenant_id, new.supplier_id)
    if supplier is None:
        raise SupplierNotFoundError
    costs = repo.product_costs(tenant_id, [line.product_id for line in new.lines])
    if len(costs) != len({line.product_id for line in new.lines}):
        raise ProductsNotFoundError
    figures = [
        ReceiptLineFigures(line.qty, line.unit_cost, costs[line.product_id]) for line in new.lines
    ]
    return repo.add_receipt(
        tenant_id,
        supplier,
        new.invoice_no,
        new.delivery_date,
        receipt_total(figures),
        [(line.product_id, line.qty, line.unit_cost, costs[line.product_id]) for line in new.lines],
    )


def find_receipt(
    tenant_id: int, receipt_id: int, repo: ReceiptRepository = receipt_repository
) -> StockReceipt | None:
    return repo.receipt(tenant_id, receipt_id)


def receipt_lines(
    receipt: StockReceipt, repo: ReceiptRepository = receipt_repository
) -> list[StockReceiptLine]:
    return repo.lines(receipt)


def receipt_history(tenant_id: int, repo: ReceiptRepository = receipt_repository) -> QuerySet:
    return repo.history(tenant_id)


def confirm_receipt(
    tenant_id: int,
    user_id: int,
    receipt_id: int,
    now: datetime,
    repo: ReceiptRepository = receipt_repository,
) -> tuple[StockReceipt, list[StockReceiptLine]]:
    """Adds the stock, sets each product's cost to the new one and counts the
    total as money out on the delivery date. Confirming twice does nothing more."""
    with transaction.atomic():
        receipt = repo.locked_receipt(tenant_id, receipt_id)
        if receipt is None:
            raise ReceiptNotFoundError
        lines = repo.lines(receipt)
        if receipt.status == StockReceipt.Status.CONFIRMED:
            return receipt, lines
        _add_stock(tenant_id, user_id, receipt, lines, now)
        repo.confirm(receipt, lines, user_id, now)
        _log(tenant_id, user_id, receipt, len(lines))
    return receipt, lines


def _add_stock(
    tenant_id: int, user_id: int, receipt: StockReceipt, lines: list[StockReceiptLine], now
) -> None:
    ordered = sorted(lines, key=lambda line: line.product_id)
    sale_stock_repository.lock_levels(tenant_id, [line.product_id for line in ordered])
    movements = [
        StockMovement(
            tenant_id=tenant_id,
            product_id=line.product_id,
            type=StockMovement.Type.RECEIVE,
            qty_delta=line.qty,
            ref_type="receipt",
            ref_id=str(receipt.id),
            reason="received",
            user_id=user_id,
            occurred_at=now,
        )
        for line in ordered
    ]
    deltas = {line.product_id: line.qty for line in ordered}
    sale_stock_repository.record(tenant_id, movements, deltas, now)


def _log(tenant_id: int, user_id: int, receipt: StockReceipt, line_count: int) -> None:
    record_activity(
        ActivityEntry(
            tenant_id=tenant_id,
            user_id=user_id,
            action="stock_received",
            entity_type="stock_receipt",
            entity_id=str(receipt.id),
            detail={
                "supplier": receipt.supplier.name,
                "invoice_no": receipt.invoice_no,
                "lines": line_count,
                "total_cost": str(receipt.total_cost),
            },
        )
    )


def cost_increase_lines(lines: list[StockReceiptLine]) -> list[StockReceiptLine]:
    return [
        line
        for line in lines
        if costs_more(ReceiptLineFigures(line.qty, line.unit_cost, line.prev_cost))
    ]
