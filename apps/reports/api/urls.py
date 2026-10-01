from django.urls import path

from .views import (
    CashiersView,
    CategoriesView,
    DashboardView,
    ExportView,
    MoneyView,
    RefundsByCashierView,
    SummaryView,
    TopProductsView,
)

urlpatterns = [
    path("reports/dashboard", DashboardView.as_view(), name="report-dashboard"),
    path("reports/summary", SummaryView.as_view(), name="report-summary"),
    path("reports/categories", CategoriesView.as_view(), name="report-categories"),
    path("reports/cashiers", CashiersView.as_view(), name="report-cashiers"),
    path("reports/top-products", TopProductsView.as_view(), name="report-top-products"),
    path("reports/money", MoneyView.as_view(), name="report-money"),
    path(
        "reports/refunds-by-cashier",
        RefundsByCashierView.as_view(),
        name="report-refunds-by-cashier",
    ),
    path("reports/export", ExportView.as_view(), name="report-export"),
]
