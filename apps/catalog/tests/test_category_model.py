import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import Category


@pytest.mark.django_db
def test_category_name_is_unique_per_tenant_ignoring_case():
    Category.objects.create(tenant_id=1, name="Grocery", tint="green")

    with pytest.raises(IntegrityError), transaction.atomic():
        Category.objects.create(tenant_id=1, name="GROCERY", tint="blue")


@pytest.mark.django_db
def test_same_category_name_is_allowed_in_another_tenant():
    Category.objects.create(tenant_id=1, name="Grocery", tint="green")
    Category.objects.create(tenant_id=2, name="Grocery", tint="green")

    assert Category.objects.filter(name="Grocery").count() == 2


@pytest.mark.django_db
def test_category_is_active_by_default():
    category = Category.objects.create(tenant_id=1, name="Bakery", tint="yellow")

    assert category.is_active is True
