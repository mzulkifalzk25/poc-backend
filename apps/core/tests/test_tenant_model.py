import pytest
from django.db import connection, models
from django.test.utils import isolate_apps

from apps.core.models import TenantModel


@isolate_apps("apps.core")
def _widget_model():
    class Widget(TenantModel):
        name = models.CharField(max_length=50)

        class Meta:
            app_label = "core"

    return Widget


@pytest.mark.django_db
def test_manager_filters_by_tenant():
    widget = _widget_model()
    with connection.schema_editor() as editor:
        editor.create_model(widget)
    try:
        widget.objects.create(tenant_id=1, name="a")
        widget.objects.create(tenant_id=2, name="b")
        widget.objects.create(tenant_id=1, name="c")

        names = set(widget.objects.for_tenant(1).values_list("name", flat=True))

        assert names == {"a", "c"}
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(widget)


@pytest.mark.django_db
def test_manager_without_tenant_filter_sees_every_row():
    widget = _widget_model()
    with connection.schema_editor() as editor:
        editor.create_model(widget)
    try:
        widget.objects.create(tenant_id=1, name="a")
        widget.objects.create(tenant_id=2, name="b")

        assert widget.objects.count() == 2
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(widget)
