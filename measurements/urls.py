from django.urls import path

from .views import MeasurementIngestQueryView

urlpatterns = [
    path("", MeasurementIngestQueryView.as_view(), name="measurement-ingest-query"),
]
