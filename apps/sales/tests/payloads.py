"""Request bodies for `POST /bills/batch`, shaped like the counter's upload."""

from decimal import Decimal
from uuid import uuid4

from apps.catalog.models import Product

BATCH_URL = "/api/v1/bills/batch"


def line(product: Product, qty: str = "1.000", price: str | None = None, line_no: int = 1) -> dict:
    return {
        "line_no": line_no,
        "product_id": product.id,
        "barcode": product.barcode,
        "name": product.name,
        "qty": qty,
        "unit_price": price or str(product.price),
    }


def bill(cashier_id: int, lines: list[dict], seq: int = 743, code: str = "002", **changes) -> dict:
    subtotal = sum(Decimal(item["qty"]) * Decimal(item["unit_price"]) for item in lines)
    total = subtotal.quantize(Decimal("1"))
    body = {
        "id": str(uuid4()),
        "bill_no": f"{code}{seq:06d}",
        "shift_id": str(uuid4()),
        "cashier_id": cashier_id,
        "sold_at": "2026-09-27T07:47:03Z",
        "items": lines,
        "payment": {
            "id": str(uuid4()),
            "method": "cash",
            "amount": f"{total:.2f}",
            "tendered": f"{total + 100:.2f}",
            "change_given": "100.00",
        },
        "totals": {
            "item_count": sum(int(Decimal(item["qty"])) for item in lines),
            "subtotal": f"{subtotal:.2f}",
            "tax": "0.00",
            "rounding": f"{total - subtotal:.2f}",
            "total": f"{total:.2f}",
        },
    }
    return {**body, **changes}


def batch(counter_id: int, *bills: dict) -> dict:
    return {"counter_id": counter_id, "bills": list(bills)}
