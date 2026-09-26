from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.tenants.domain.device_token import generate_device_token, hash_device_token
from apps.tenants.models import Counter, Device, DeviceCode


@pytest.fixture
def counter() -> Counter:
    return Counter.objects.create(tenant_id=1, name="Counter 1", code="001")


def test_device_tokens_are_long_random_and_hashed():
    token = generate_device_token()

    assert len(token) >= 40
    assert token != generate_device_token()
    assert hash_device_token(token) == hash_device_token(token)
    assert token not in hash_device_token(token)


@pytest.mark.django_db
def test_code_hash_is_unique(counter):
    expires_at = timezone.now() + timedelta(minutes=15)
    DeviceCode.objects.create(
        tenant_id=1, counter=counter, code_hash="a" * 64, expires_at=expires_at
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        DeviceCode.objects.create(
            tenant_id=1, counter=counter, code_hash="a" * 64, expires_at=expires_at
        )


@pytest.mark.django_db
def test_a_counter_has_at_most_one_live_device(counter):
    Device.objects.create(tenant_id=1, counter=counter, token_hash="a" * 64)

    with pytest.raises(IntegrityError), transaction.atomic():
        Device.objects.create(tenant_id=1, counter=counter, token_hash="b" * 64)


@pytest.mark.django_db
def test_revoked_devices_do_not_block_a_new_live_device(counter):
    Device.objects.create(
        tenant_id=1, counter=counter, token_hash="a" * 64, revoked_at=timezone.now()
    )

    Device.objects.create(tenant_id=1, counter=counter, token_hash="b" * 64)

    assert Device.objects.filter(counter=counter).count() == 2
