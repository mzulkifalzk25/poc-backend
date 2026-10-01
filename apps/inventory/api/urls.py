from django.urls import path

from .receipt_views import (
    ReceiptConfirmView,
    ReceiptDetailView,
    ReceiptListCreateView,
    SupplierListCreateView,
)
from .stock_views import StockAdjustView, StockListView, StockMovementsView
from .views import StockSyncView

urlpatterns = [
    path("stock", StockListView.as_view(), name="stock-list"),
    path("stock/sync/", StockSyncView.as_view(), name="stock-sync"),
    path("stock/adjust", StockAdjustView.as_view(), name="stock-adjust"),
    path("stock/movements", StockMovementsView.as_view(), name="stock-movements"),
    path("suppliers", SupplierListCreateView.as_view(), name="supplier-list-create"),
    path("stock/receipts", ReceiptListCreateView.as_view(), name="receipt-list-create"),
    path("stock/receipts/<int:receipt_id>", ReceiptDetailView.as_view(), name="receipt-detail"),
    path(
        "stock/receipts/<int:receipt_id>/confirm",
        ReceiptConfirmView.as_view(),
        name="receipt-confirm",
    ),
]
