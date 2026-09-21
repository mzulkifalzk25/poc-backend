import pytest
from django.db import connections, transaction

from apps.audit.models import ActivityLog
from apps.audit.use_cases.record_activity import ActivityEntry, record_failure


@pytest.fixture(autouse=True)
def _close_audit_connection():
    # The `audit` alias opens its own connection; close it after each test so
    # pytest-django can drop the shared test database on teardown.
    yield
    connections["audit"].close()


@pytest.mark.django_db(databases=["default", "audit"])
def test_record_failure_writes_on_the_audit_connection():
    record_failure(ActivityEntry(tenant_id=1, action="pin_failure"))

    assert ActivityLog.objects.using("audit").filter(tenant_id=1, action="pin_failure").exists()


@pytest.mark.django_db(databases=["default", "audit"])
def test_failure_entry_survives_a_rollback_of_the_default_transaction():
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), transaction.atomic():
        record_failure(ActivityEntry(tenant_id=1, action="pin_failure"))
        raise _Boom

    assert ActivityLog.objects.using("audit").filter(tenant_id=1, action="pin_failure").exists()
