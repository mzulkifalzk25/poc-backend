from dataclasses import dataclass
from decimal import Decimal

from apps.sales.domain.bill_number import is_valid_bill_no, normalize_bill_no
from apps.sales.domain.errors import BillNotFoundError
from apps.sales.repositories.bills import BillRepository, bill_repository


@dataclass(frozen=True)
class LookupLine:
    product_id: int
    name: str
    qty: Decimal
    unit_price: Decimal
    returnable_qty: Decimal


@dataclass(frozen=True)
class BillLookup:
    bill_no: str
    lines: list[LookupLine]


def lookup_bill(tenant_id: int, text: str, bills: BillRepository = bill_repository) -> BillLookup:
    """Any counter's bill in the store. Returnable = sold until returns exist
    (Step B6 subtracts what was already returned)."""
    bill_no = normalize_bill_no(text)
    bill = bills.by_bill_no(tenant_id, bill_no) if is_valid_bill_no(bill_no) else None
    if bill is None:
        raise BillNotFoundError
    lines = [
        LookupLine(item.product_id, item.name_snapshot, item.qty, item.unit_price, item.qty)
        for item in bills.items_of(bill)
    ]
    return BillLookup(bill.bill_no, lines)
