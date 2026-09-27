from decimal import Decimal

from rest_framework import serializers

from apps.sales.domain.bill_number import is_valid_bill_no
from apps.sales.domain.lines import SaleLine
from apps.sales.use_cases.bill_upload import BillUpload, PaymentUpload, SentTotals

MAX_BILLS = 100
MAX_LINES = 500


def _money(**kwargs) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=12, decimal_places=2, **kwargs)


class BatchRequestSerializer(serializers.Serializer):
    counter_id = serializers.IntegerField()
    bills = serializers.ListField(
        child=serializers.JSONField(), allow_empty=False, max_length=MAX_BILLS
    )


class ItemSerializer(serializers.Serializer):
    line_no = serializers.IntegerField(min_value=1)
    product_id = serializers.IntegerField()
    barcode = serializers.CharField(max_length=64, allow_blank=True)
    name = serializers.CharField(max_length=255)
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = _money(min_value=0)


class PaymentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    method = serializers.ChoiceField(choices=["cash", "card", "wallet"])
    amount = _money(min_value=0)
    tendered = _money(min_value=0, required=False, allow_null=True)
    change_given = _money(min_value=0, required=False, allow_null=True)
    reference = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class TotalsSerializer(serializers.Serializer):
    item_count = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    subtotal = _money(min_value=0)
    tax = _money(min_value=0)
    rounding = _money()
    total = _money(min_value=0)


class BillSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    bill_no = serializers.CharField(max_length=20)
    shift_id = serializers.UUIDField()
    cashier_id = serializers.IntegerField()
    sold_at = serializers.DateTimeField()
    items = ItemSerializer(many=True, allow_empty=False, max_length=MAX_LINES)
    payment = PaymentSerializer()
    totals = TotalsSerializer()

    def validate_bill_no(self, value: str) -> str:
        if not is_valid_bill_no(value):
            raise serializers.ValidationError("A bill number is 9 digits.")
        return value


def to_bill_upload(data: dict) -> BillUpload:
    payment = data["payment"]
    return BillUpload(
        id=data["id"],
        bill_no=data["bill_no"],
        shift_id=data["shift_id"],
        cashier_id=data["cashier_id"],
        sold_at=data["sold_at"],
        lines=[SaleLine(**item) for item in data["items"]],
        payment=PaymentUpload(
            id=payment["id"],
            method=payment["method"],
            amount=payment["amount"],
            tendered=payment.get("tendered"),
            change_given=payment.get("change_given"),
            reference=payment["reference"],
        ),
        totals=SentTotals(**data["totals"]),
    )


def flat_errors(errors, prefix: str = "") -> list[str]:
    """`{"items": [{}, {"qty": ["..."]}]}` becomes `["items.1.qty: ..."]`."""
    if isinstance(errors, dict):
        return [
            text for key, value in errors.items() for text in flat_errors(value, f"{prefix}{key}.")
        ]
    if isinstance(errors, list) and errors and not isinstance(errors[0], str):
        return [
            text
            for index, value in enumerate(errors)
            for text in flat_errors(value, f"{prefix}{index}.")
        ]
    return [f"{prefix.rstrip('.') or 'bill'}: {message}" for message in errors]
