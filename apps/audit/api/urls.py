from django.urls import path

from .views import EventBatchView

urlpatterns = [
    path("audit/events/batch", EventBatchView.as_view(), name="audit-event-batch"),
]
