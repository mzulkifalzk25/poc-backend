import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User


@pytest.mark.django_db
def test_owner_password_is_hashed_and_checkable():
    user = User(tenant_id=1, full_name="Sana Ahmed", role="owner", username="sana")
    user.set_password("correct horse battery staple")
    user.save()

    assert user.password != "correct horse battery staple"
    assert user.check_password("correct horse battery staple")
    assert not user.check_password("wrong")


@pytest.mark.django_db
def test_duplicate_cashier_full_name_in_same_tenant_is_rejected():
    User.objects.create(tenant_id=1, full_name="Zainab Khan", role="cashier", pin_hash="x")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(tenant_id=1, full_name="zainab khan", role="cashier", pin_hash="y")


@pytest.mark.django_db
def test_duplicate_cashier_full_name_across_tenants_is_allowed():
    User.objects.create(tenant_id=1, full_name="Zainab Khan", role="cashier", pin_hash="x")
    User.objects.create(tenant_id=2, full_name="Zainab Khan", role="cashier", pin_hash="y")

    assert User.objects.filter(full_name="Zainab Khan").count() == 2


@pytest.mark.django_db
def test_duplicate_email_in_same_tenant_is_rejected_case_insensitively():
    User.objects.create(tenant_id=1, full_name="Sana Ahmed", role="owner", email="Sana@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(
            tenant_id=1, full_name="Someone Else", role="owner", email="sana@example.com"
        )


@pytest.mark.django_db
def test_same_email_in_different_tenants_is_allowed():
    User.objects.create(tenant_id=1, full_name="Sana Ahmed", role="owner", email="sana@example.com")
    User.objects.create(tenant_id=2, full_name="Sana Ahmed", role="owner", email="sana@example.com")

    assert User.objects.filter(email__iexact="sana@example.com").count() == 2
