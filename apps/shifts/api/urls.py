from django.urls import path

from .views import CurrentShiftView, OpenShiftView

urlpatterns = [
    path("shifts/open", OpenShiftView.as_view(), name="shift-open"),
    path("shifts/current", CurrentShiftView.as_view(), name="shift-current"),
]
