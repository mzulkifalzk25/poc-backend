from django.urls import path

from .bill_views import BillBatchView, BillLookupView
from .held_views import HeldBillSyncView

urlpatterns = [
    path("bills/batch", BillBatchView.as_view(), name="bill-batch"),
    path("bills/lookup", BillLookupView.as_view(), name="bill-lookup"),
    path("held-bills/sync", HeldBillSyncView.as_view(), name="held-bill-sync"),
]
