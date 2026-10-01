from django.urls import path

from .browse_views import ActivityLogExportView, ActivityLogView
from .views import EventBatchView

urlpatterns = [
    path("audit/events/batch", EventBatchView.as_view(), name="audit-event-batch"),
    path("activity-log", ActivityLogView.as_view(), name="activity-log"),
    path("activity-log/export", ActivityLogExportView.as_view(), name="activity-log-export"),
]
