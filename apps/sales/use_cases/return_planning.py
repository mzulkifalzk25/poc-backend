"""Checks each uploaded return against the store's data before anything is
written: duplicates, unknown references (rejected) and anomalies (flags)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.catalog.domain.price_history import PriceChange, price_in_force
from apps.catalog.models import Product
from apps.core.domain.money import Money
from apps.sales.domain.bill_number import normalize_bill_no
from apps.sales.domain.flags import CLOCK_SKEW, PRICE_MISMATCH, is_clock_skewed
from apps.sales.domain.returns import Refund, TodayPrice, merge_returned, price_return
from apps.sales.domain.totals import TaxRule, total_differs
from apps.sales.repositories.returns import LockedBill

from .bill_upload import DUPLICATE, REJECTED
from .return_upload import ReturnResult, ReturnUpload


@dataclass
class ReturnContext:
    tax: TaxRule
    received_at: datetime
    token_cashier_id: int | None
    products: dict[int, Product]
    price_changes: dict[int, list[PriceChange]]
    user_ids: set[int]
    shift_cashiers: dict[UUID, int]
    stored_flags: dict[UUID, list[str]]
    bills: dict[str, LockedBill]
    seen_ids: set[UUID]


@dataclass
class PlannedReturn:
    upload: ReturnUpload
    cashier_id: int
    bill: LockedBill | None
    refund: Refund
    flags: set[str]


def plan_return(upload: ReturnUpload, ctx: ReturnContext) -> ReturnResult | PlannedReturn:
    if upload.id in ctx.stored_flags:
        return ReturnResult(str(upload.id), DUPLICATE, ctx.stored_flags[upload.id])
    if upload.id in ctx.seen_ids:
        return ReturnResult(str(upload.id), DUPLICATE)
    ctx.seen_ids.add(upload.id)
    cashier_id = _cashier(upload, ctx)
    errors = _reference_errors(upload, cashier_id, ctx)
    if errors or cashier_id is None:
        return ReturnResult(str(upload.id), REJECTED, [], errors)
    bill = ctx.bills.get(bill_key(upload.original_bill_no)) if upload.original_bill_no else None
    refund = price_return(
        merge_returned(upload.lines),
        bill.found if bill else None,
        upload.original_bill_no is not None,
        _today(upload, ctx),
        ctx.tax,
    )
    return PlannedReturn(upload, cashier_id, bill, refund, _flags(upload, refund, ctx))


def bill_key(typed: str | None) -> str:
    return normalize_bill_no(typed or "")


def _cashier(upload: ReturnUpload, ctx: ReturnContext) -> int | None:
    """The signed-in cashier; for a PC token the body's cashier, else the
    cashier who opened the return's shift."""
    if ctx.token_cashier_id is not None:
        return ctx.token_cashier_id
    if upload.cashier_id is not None:
        return upload.cashier_id if upload.cashier_id in ctx.user_ids else None
    return ctx.shift_cashiers.get(upload.shift_id)


def _reference_errors(
    upload: ReturnUpload, cashier_id: int | None, ctx: ReturnContext
) -> list[str]:
    errors = [
        f"lines.{index}.product_id: Unknown product."
        for index, line in enumerate(upload.lines)
        if line.product_id not in ctx.products
    ]
    if cashier_id is None:
        errors.append("cashier_id: Unknown cashier.")
    return errors


def _today(upload: ReturnUpload, ctx: ReturnContext) -> dict[int, TodayPrice]:
    today = {}
    for line in upload.lines:
        product = ctx.products[line.product_id]
        changes = ctx.price_changes.get(line.product_id, [])
        price = price_in_force(product.price, changes, upload.returned_at)
        today[line.product_id] = TodayPrice(price, product.cost)
    return today


def _flags(upload: ReturnUpload, refund: Refund, ctx: ReturnContext) -> set[str]:
    checks = {
        PRICE_MISMATCH: total_differs(Money(upload.refund_amount), refund.total),
        CLOCK_SKEW: is_clock_skewed(upload.returned_at, ctx.received_at),
    }
    return refund.flags | {flag for flag, raised in checks.items() if raised}
