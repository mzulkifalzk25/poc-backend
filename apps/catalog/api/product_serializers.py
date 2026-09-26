from decimal import Decimal

from rest_framework import serializers

from apps.catalog.domain.product_rules import UNITS, normalize_barcode, normalize_product_name

_MONEY = {"max_digits": 12, "decimal_places": 2, "min_value": Decimal("0")}
_QTY = {"max_digits": 12, "decimal_places": 3}


class ProductWriteSerializer(serializers.Serializer):
    """Money and quantities arrive as strings; `stock` is create-only."""

    barcode = serializers.CharField(max_length=64, trim_whitespace=False)
    name = serializers.CharField(max_length=255)
    category_id = serializers.IntegerField()
    unit = serializers.ChoiceField(choices=UNITS)
    price = serializers.DecimalField(**_MONEY)
    cost = serializers.DecimalField(**_MONEY)
    low_stock_alert = serializers.DecimalField(
        **_QTY, min_value=Decimal("0"), required=False, default=Decimal("0")
    )

    def validate_barcode(self, value: str) -> str:
        barcode = normalize_barcode(value)
        if barcode is None:
            raise serializers.ValidationError("Barcode must be 1 to 64 characters without spaces.")
        return barcode

    def validate_name(self, value: str) -> str:
        name = normalize_product_name(value)
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name


class ProductCreateSerializer(ProductWriteSerializer):
    stock = serializers.DecimalField(
        **_QTY, min_value=Decimal("0"), required=False, default=Decimal("0")
    )


class ProductFilterSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=100)
    category = serializers.IntegerField(required=False)
    stock = serializers.ChoiceField(choices=["all", "low", "out"], required=False, default="all")
    archived = serializers.BooleanField(required=False, default=False)
