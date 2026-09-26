from django.urls import path

from .pos_views import PeopleSyncView, PinLoginView, RosterView
from .staff_views import StaffDetailView, StaffListCreateView
from .views import LoginView, LogoutView, MeView, RefreshView

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/pin-login", PinLoginView.as_view(), name="auth-pin-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="me"),
    path("pos/roster", RosterView.as_view(), name="pos-roster"),
    path("pos/people/sync/", PeopleSyncView.as_view(), name="pos-people-sync"),
    path("users", StaffListCreateView.as_view(), name="user-list-create"),
    path("users/<int:user_id>", StaffDetailView.as_view(), name="user-detail"),
]
