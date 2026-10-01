from decimal import Decimal

from rest_framework import serializers

from apps.core.domain.cursor import Cursor
from apps.inventory.domain.adjustment import MODES, REASONS

_QTY = {"max_digits": 12, "decimal_places": 3}
_MONEY = {"max_digits": 12, "decimal_places": 2, "min_value": Decimal("0")}
MOVEMENT_TYPES = (
    "sale",
    "return",
    "receive",
    "adjust_add",
    "adjust_remove",
    "count_correction",
    "adjust",
)


class StockFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["all", "low", "out", "negative"], required=False, default="all"
    )
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)


class AdjustSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    mode = serializers.ChoiceField(choices=MODES)
    qty = serializers.DecimalField(**_QTY, min_value=Decimal("0"))
    reason = serializers.ChoiceField(choices=REASONS)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")

    def validate(self, data: dict) -> dict:
        if data["mode"] in ("add", "remove") and data["qty"] <= 0:
            raise serializers.ValidationError({"qty": ["Enter a quantity above 0."]})
        return data


class MovementFilterSerializer(serializers.Serializer):
    product = serializers.IntegerField(required=False)
    type = serializers.CharField(required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    cursor = serializers.CharField(required=False, allow_blank=True)
    since = serializers.DateTimeField(required=False)
    until = serializers.DateTimeField(required=False)

    def validate_type(self, value: str) -> list[str]:
        types: list[str] = []
        for name in filter(None, value.split(",")):
            if name not in MOVEMENT_TYPES:
                raise serializers.ValidationError(f"Unknown movement type {name}.")
            types.extend(
                ["adjust_add", "adjust_remove", "count_correction"] if name == "adjust" else [name]
            )
        return types

    def validate_cursor(self, value: str) -> Cursor | None:
        if not value:
            return None
        try:
            return Cursor.decode(value)
        except ValueError:
            raise serializers.ValidationError("Invalid cursor.") from None


class SupplierSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")

    def validate_name(self, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name


class ReceiptLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(**_QTY, min_value=Decimal("0.001"))
    unit_cost = serializers.DecimalField(**_MONEY)


class ReceiptSerializer(serializers.Serializer):
    supplier_id = serializers.IntegerField()
    invoice_no = serializers.CharField(required=False, allow_blank=True, max_length=64, default="")
    delivery_date = serializers.DateField()
    lines = ReceiptLineSerializer(many=True, allow_empty=False)

    def validate_lines(self, lines: list[dict]) -> list[dict]:
        ids = [line["product_id"] for line in lines]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product can appear once.")
        return lines
