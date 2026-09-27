from rest_framework import serializers


def money_field(**kwargs) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, **kwargs)


class OpenShiftRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    counter_id = serializers.IntegerField()
    opened_at = serializers.DateTimeField()
    opening_cash = money_field()
    cashier_id = serializers.IntegerField(required=False, allow_null=True)
