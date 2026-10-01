from decimal import Decimal

from apps.catalog.api.product_presenters import present_product
from apps.inventory.models import StockMovement, StockReceipt, StockReceiptLine, Supplier


def _moment(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def present_stock_row(product) -> dict:
    return {
        **present_product(product, product.qty, include_cost=True),
        "low_stock_alert": str(product.low_stock_alert),
    }


def present_summary(summary: dict) -> dict:
    return {
        "units_in_stock": str(summary["units"].quantize(Decimal("0.001"))),
        "stock_value": str(summary["value"].quantize(Decimal("0.01"))),
        "low_count": summary["low"],
        "out_count": summary["out"],
    }


def present_movement(movement: StockMovement, users: dict[int, str]) -> dict:
    return {
        "id": movement.id,
        "occurred_at": _moment(movement.occurred_at),
        "product": {"id": movement.product_id, "name": movement.product.name},
        "type": movement.type,
        "qty_delta": str(movement.qty_delta),
        "reason": movement.reason,
        "note": movement.note,
        "user": users.get(movement.user_id) if movement.user_id else None,
    }


def present_supplier(supplier: Supplier) -> dict:
    return {"id": supplier.id, "name": supplier.name, "phone": supplier.phone}


def present_receipt(receipt: StockReceipt, lines: list[StockReceiptLine] | None = None) -> dict:
    row = {
        "id": receipt.id,
        "supplier": {"id": receipt.supplier_id, "name": receipt.supplier.name},
        "invoice_no": receipt.invoice_no,
        "delivery_date": receipt.delivery_date.isoformat(),
        "total_cost": str(receipt.total_cost),
        "status": receipt.status,
        "confirmed_at": _moment(receipt.confirmed_at) if receipt.confirmed_at else None,
    }
    if lines is not None:
        row["lines"] = [present_line(line) for line in lines]
    return row


def present_line(line: StockReceiptLine) -> dict:
    return {
        "product_id": line.product_id,
        "name": line.product.name,
        "barcode": line.product.barcode,
        "qty": str(line.qty),
        "unit_cost": str(line.unit_cost),
        "prev_cost": str(line.prev_cost),
    }
