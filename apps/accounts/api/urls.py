from django.urls import path

from .pos_views import (
    BootstrapView,
    HeartbeatView,
    PeopleSyncView,
    PinLoginView,
    RosterView,
)
from .staff_views import ResetPinView, StaffDetailView, StaffListCreateView, UnlockView
from .views import LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/pin-login", PinLoginView.as_view(), name="auth-pin-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="me"),
    path("pos/bootstrap", BootstrapView.as_view(), name="pos-bootstrap"),
    path("counters/<int:counter_id>/heartbeat", HeartbeatView.as_view(), name="counter-heartbeat"),
    path("pos/roster", RosterView.as_view(), name="pos-roster"),
    path("pos/people/sync/", PeopleSyncView.as_view(), name="pos-people-sync"),
    path("users", StaffListCreateView.as_view(), name="user-list-create"),
    path("users/<int:user_id>", StaffDetailView.as_view(), name="user-detail"),
    path("users/<int:user_id>/unlock", UnlockView.as_view(), name="user-unlock"),
    path("users/<int:user_id>/reset-pin", ResetPinView.as_view(), name="user-reset-pin"),
]
