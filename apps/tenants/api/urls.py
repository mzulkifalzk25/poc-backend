from django.urls import path

from .device_views import DeviceCodeCreateView, DeviceCodeRevokeView
from .views import CounterDetailView, CounterListCreateView, TenantSettingsView

urlpatterns = [
    path("tenant/settings", TenantSettingsView.as_view(), name="tenant-settings"),
    path("counters", CounterListCreateView.as_view(), name="counter-list-create"),
    path("counters/<int:pk>", CounterDetailView.as_view(), name="counter-detail"),
    path("devices/codes", DeviceCodeCreateView.as_view(), name="device-code-create"),
    path(
        "devices/codes/<int:counter_id>",
        DeviceCodeRevokeView.as_view(),
        name="device-code-revoke",
    ),
]
