from django.urls import path

from .product_views import (
    ProductArchiveView,
    ProductByBarcodeView,
    ProductDetailView,
    ProductListCreateView,
    ProductPriceHistoryView,
    ProductRestoreView,
)
from .sync_views import ProductSyncView
from .views import CategoryDetailView, CategoryListCreateView, CategoryMoveProductsView

urlpatterns = [
    path("categories", CategoryListCreateView.as_view(), name="category-list-create"),
    path("categories/<int:category_id>", CategoryDetailView.as_view(), name="category-detail"),
    path(
        "categories/<int:category_id>/move-products",
        CategoryMoveProductsView.as_view(),
        name="category-move-products",
    ),
    path("products", ProductListCreateView.as_view(), name="product-list-create"),
    path("products/sync/", ProductSyncView.as_view(), name="product-sync"),
    path("products/<int:product_id>", ProductDetailView.as_view(), name="product-detail"),
    path("products/<int:product_id>/archive", ProductArchiveView.as_view(), name="product-archive"),
    path("products/<int:product_id>/restore", ProductRestoreView.as_view(), name="product-restore"),
    path(
        "products/<int:product_id>/price-history",
        ProductPriceHistoryView.as_view(),
        name="product-price-history",
    ),
    path(
        "products/by-barcode/<str:code>",
        ProductByBarcodeView.as_view(),
        name="product-by-barcode",
    ),
]
