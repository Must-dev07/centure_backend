from django.urls import path

from .views import (
    AlertAcknowledgeView,
    AlertDetailView,
    AlertListView,
    AlertResolveView,
    ReportBleLostView,
)

urlpatterns = [
    path("", AlertListView.as_view(), name="alert-list"),
    path("<int:pk>/", AlertDetailView.as_view(), name="alert-detail"),
    path("<int:pk>/acknowledge/", AlertAcknowledgeView.as_view(), name="alert-acknowledge"),
    path("<int:pk>/resolve/", AlertResolveView.as_view(), name="alert-resolve"),
    path("report-ble-lost/", ReportBleLostView.as_view(), name="alert-report-ble-lost"),
]
