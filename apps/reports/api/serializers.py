from rest_framework import serializers


class RangeSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to = serializers.DateField()


class SummaryQuerySerializer(RangeSerializer):
    group = serializers.ChoiceField(choices=["hour", "day", "week"], default="day")


class MoneyQuerySerializer(RangeSerializer):
    group = serializers.ChoiceField(choices=["day", "month"], default="day")


class TopProductsQuerySerializer(RangeSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10)


class DashboardQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)


class ExportQuerySerializer(RangeSerializer):
    report = serializers.ChoiceField(choices=["money", "refunds_by_cashier", "summary"])
    group = serializers.ChoiceField(choices=["hour", "day", "week", "month"], default="day")
