from rest_framework import serializers

from apps.sales.domain.bill_cursor import BillCursor
from apps.sales.domain.bill_search import bill_no_digits
from apps.sales.models import Bill, Payment


class BillFilterSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    from_date = serializers.DateField(required=False)
    to = serializers.DateField(required=False)
    cashier = serializers.IntegerField(required=False)
    payment = serializers.ChoiceField(choices=Payment.Method.values, required=False)
    status = serializers.ChoiceField(choices=Bill.Status.values, required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=20)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=25)
    cursor = serializers.CharField(required=False, allow_blank=True)

    def validate_search(self, value: str) -> str:
        return bill_no_digits(value)

    def validate_cursor(self, value: str) -> BillCursor | None:
        if not value:
            return None
        try:
            return BillCursor.decode(value)
        except ValueError:
            raise serializers.ValidationError("Invalid cursor.") from None
