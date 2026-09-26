from django.urls import path

from .product_views import ProductListCreateView
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
]
