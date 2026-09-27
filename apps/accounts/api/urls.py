from django.urls import path

from .pos_views import BootstrapView, CashierLoginView, HeartbeatView
from .staff_views import ResetPasswordView, StaffDetailView, StaffListCreateView
from .views import LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/cashier-login", CashierLoginView.as_view(), name="auth-cashier-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="me"),
    path("pos/bootstrap", BootstrapView.as_view(), name="pos-bootstrap"),
    path("counters/<int:counter_id>/heartbeat", HeartbeatView.as_view(), name="counter-heartbeat"),
    path("users", StaffListCreateView.as_view(), name="user-list-create"),
    path("users/<int:user_id>", StaffDetailView.as_view(), name="user-detail"),
    path(
        "users/<int:user_id>/reset-password",
        ResetPasswordView.as_view(),
        name="user-reset-password",
    ),
]
