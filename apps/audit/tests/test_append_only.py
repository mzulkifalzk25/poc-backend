import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.audit.models import ActivityLog


@pytest.mark.django_db
def test_update_is_rejected_by_the_database():
    row = ActivityLog.objects.create(
        tenant_id=1, action="product_created", occurred_at=timezone.now()
    )

    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE audit_activitylog SET action = %s WHERE id = %s",
                ["product_archived", row.id],
            )


@pytest.mark.django_db
def test_delete_is_rejected_by_the_database():
    row = ActivityLog.objects.create(
        tenant_id=1, action="product_created", occurred_at=timezone.now()
    )

    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM audit_activitylog WHERE id = %s", [row.id])
