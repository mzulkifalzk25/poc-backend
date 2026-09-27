from django.urls import path

from .views import CloseShiftView, CurrentShiftView, OpenShiftView

urlpatterns = [
    path("shifts/open", OpenShiftView.as_view(), name="shift-open"),
    path("shifts/current", CurrentShiftView.as_view(), name="shift-current"),
    path("shifts/<uuid:shift_id>/close", CloseShiftView.as_view(), name="shift-close"),
]
