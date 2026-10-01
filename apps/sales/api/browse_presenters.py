from apps.sales.models import Bill, Return


def _moment(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _method(bill: Bill) -> str | None:
    payments = list(bill.payments.all())
    return payments[0].method if payments else None


def present_bill_row(bill: Bill) -> dict:
    return {
        "id": str(bill.id),
        "bill_no": bill.bill_no,
        "time": _moment(bill.sold_at),
        "cashier": bill.cashier.full_name,
        "items": str(bill.item_count),
        "payment": _method(bill),
        "total": str(bill.total),
        "status": bill.status,
    }


def present_return(record: Return) -> dict:
    return {
        "id": str(record.id),
        "returned_at": _moment(record.returned_at),
        "refund_total": str(record.refund_total),
        "refund_method": record.refund_method,
        "reason": record.reason,
        "items": len(record.items.all()),
    }


def present_bill_detail(bill: Bill, returns: list[Return]) -> dict:
    payments = list(bill.payments.all())
    payment = payments[0] if payments else None
    return {
        **present_bill_row(bill),
        "cashier": {"id": bill.cashier_id, "name": bill.cashier.full_name},
        "counter": {"id": bill.counter_id, "name": bill.counter.name, "code": bill.counter.code},
        "payment": {
            "method": payment.method,
            "amount": str(payment.amount),
            "tendered": str(payment.tendered) if payment.tendered is not None else None,
            "change_given": str(payment.change_given) if payment.change_given is not None else None,
        }
        if payment
        else None,
        "items": [
            {
                "line_no": item.line_no,
                "name": item.name_snapshot,
                "barcode": item.barcode_snapshot,
                "qty": str(item.qty),
                "unit_price": str(item.unit_price),
                "line_total": str(item.line_total),
            }
            for item in sorted(bill.items.all(), key=lambda item: item.line_no)
        ],
        "totals": {
            "subtotal": str(bill.subtotal),
            "tax": str(bill.tax_amount),
            "rounding": str(bill.rounding),
            "total": str(bill.total),
        },
        "flags": list(bill.flags),
        "returns": [present_return(record) for record in returns],
    }
