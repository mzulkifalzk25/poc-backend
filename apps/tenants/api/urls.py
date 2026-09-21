from django.urls import path

from .views import TenantSettingsView

urlpatterns = [
    path("tenant/settings", TenantSettingsView.as_view(), name="tenant-settings"),
]
