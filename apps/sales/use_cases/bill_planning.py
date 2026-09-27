"""Checks each uploaded bill against the store's data before anything is
written: duplicates, unknown references (rejected) and anomalies (flags)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from apps.catalog.domain.price_history import PriceChange, price_in_force
from apps.catalog.models import Product
from apps.core.domain.money import Money
from apps.sales.domain.flags import (
    BILL_NO_CONFLICT,
    CLOCK_SKEW,
    PRICE_MISMATCH,
    TOTAL_MISMATCH,
    is_bill_no_conflict,
    is_clock_skewed,
)
from apps.sales.domain.lines import SaleLine, merge_lines
from apps.sales.domain.totals import TaxRule, bill_totals, total_differs

from .bill_upload import DUPLICATE, BillResult, BillUpload, rejected


@dataclass
class BatchContext:
    counter_code: str
    tax: TaxRule
    received_at: datetime
    app_version: str
    products: dict[int, Product]
    price_changes: dict[int, list[PriceChange]]
    user_ids: set[int]
    stored_flags: dict[UUID, list[str]]
    taken_bill_nos: set[str]
    seen_ids: set[UUID]


@dataclass
class PlannedBill:
    upload: BillUpload
    lines: list[SaleLine]
    flags: set[str]


def plan_bill(upload: BillUpload, ctx: BatchContext) -> BillResult | PlannedBill:
    if upload.id in ctx.stored_flags:
        return BillResult(str(upload.id), DUPLICATE, upload.bill_no, ctx.stored_flags[upload.id])
    if upload.id in ctx.seen_ids:
        return BillResult(str(upload.id), DUPLICATE, upload.bill_no)
    ctx.seen_ids.add(upload.id)
    errors = _reference_errors(upload, ctx)
    if errors:
        return rejected(str(upload.id), upload.bill_no, errors)
    lines = merge_lines(upload.lines)
    flags = _flags(upload, lines, ctx)
    ctx.taken_bill_nos.add(upload.bill_no)
    return PlannedBill(upload, lines, flags)


def _reference_errors(upload: BillUpload, ctx: BatchContext) -> list[str]:
    errors = [
        f"items.{index}.product_id: Unknown product."
        for index, line in enumerate(upload.lines)
        if line.product_id not in ctx.products
    ]
    if upload.cashier_id not in ctx.user_ids:
        errors.append("cashier_id: Unknown cashier.")
    return errors


def _flags(upload: BillUpload, lines: list[SaleLine], ctx: BatchContext) -> set[str]:
    computed = bill_totals(lines, ctx.tax).total
    checks = {
        PRICE_MISMATCH: any(_price_differs(line, upload.sold_at, ctx) for line in upload.lines),
        CLOCK_SKEW: is_clock_skewed(upload.sold_at, ctx.received_at),
        TOTAL_MISMATCH: total_differs(Money(upload.totals.total), computed),
        BILL_NO_CONFLICT: is_bill_no_conflict(
            upload.bill_no, ctx.counter_code, upload.bill_no in ctx.taken_bill_nos
        ),
    }
    return {flag for flag, raised in checks.items() if raised}


def _price_differs(line: SaleLine, sold_at: datetime, ctx: BatchContext) -> bool:
    product = ctx.products[line.product_id]
    changes = ctx.price_changes.get(line.product_id, [])
    return line.unit_price != price_in_force(product.price, changes, sold_at)
