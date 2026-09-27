from decimal import Decimal

from rest_framework import serializers

from apps.sales.domain.returns import ReturnedQty
from apps.sales.models import Return
from apps.sales.use_cases.return_upload import ReturnUpload

MAX_RETURNS = 50
MAX_LINES = 500


class ReturnBatchRequestSerializer(serializers.Serializer):
    returns = serializers.ListField(
        child=serializers.JSONField(), allow_empty=False, max_length=MAX_RETURNS
    )


class ReturnLineSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))


class RefundSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["cash", "card", "wallet"])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)


class ReturnSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    shift_id = serializers.UUIDField()
    lines = ReturnLineSerializer(many=True, allow_empty=False, max_length=MAX_LINES)
    reason = serializers.ChoiceField(choices=Return.Reason.values)
    restock = serializers.BooleanField()
    refund = RefundSerializer()
    original_bill_no = serializers.CharField(
        max_length=20, required=False, allow_null=True, allow_blank=True
    )
    returned_at = serializers.DateTimeField()
    cashier_id = serializers.IntegerField(required=False, allow_null=True)


def to_return_upload(data: dict) -> ReturnUpload:
    typed = (data.get("original_bill_no") or "").strip()
    return ReturnUpload(
        id=data["id"],
        shift_id=data["shift_id"],
        lines=[ReturnedQty(line["product_id"], line["qty"]) for line in data["lines"]],
        reason=data["reason"],
        restock=data["restock"],
        refund_method=data["refund"]["method"],
        refund_amount=data["refund"]["amount"],
        original_bill_no=typed or None,
        returned_at=data["returned_at"],
        cashier_id=data.get("cashier_id"),
    )
