from django.urls import path

from .views import CounterDetailView, CounterListCreateView, TenantSettingsView

urlpatterns = [
    path("tenant/settings", TenantSettingsView.as_view(), name="tenant-settings"),
    path("counters", CounterListCreateView.as_view(), name="counter-list-create"),
    path("counters/<int:pk>", CounterDetailView.as_view(), name="counter-detail"),
]
