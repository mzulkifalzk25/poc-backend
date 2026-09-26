from rest_framework import serializers

from apps.catalog.domain.category_rules import TINTS, normalize_category_name
from apps.catalog.models import Category


class CategoryWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    tint = serializers.ChoiceField(choices=TINTS)

    def validate_name(self, value: str) -> str:
        name = normalize_category_name(value)
        if not name:
            raise serializers.ValidationError("Name is required.")
        return name


class MoveProductsSerializer(serializers.Serializer):
    to_category_id = serializers.IntegerField()


def present_category(category: Category) -> dict:
    """`product_count` counts live products; 0 until products exist."""
    return {
        "id": category.id,
        "name": category.name,
        "tint": category.tint,
        "product_count": getattr(category, "product_count", 0),
    }
