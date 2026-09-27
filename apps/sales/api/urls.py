from django.urls import path

from .bill_views import BillBatchView

urlpatterns = [
    path("bills/batch", BillBatchView.as_view(), name="bill-batch"),
]
