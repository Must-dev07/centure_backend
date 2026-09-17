from django.urls import path

from .views import (
    DeviceTokenRegisterView,
    NotificationDetailView,
    NotificationListView,
    NotificationPreferencesView,
    NotificationReadAllView,
    NotificationReadView,
)

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path("read-all/", NotificationReadAllView.as_view(), name="notification-read-all"),
    path("preferences/", NotificationPreferencesView.as_view(), name="notification-preferences"),
    path("<int:pk>/read/", NotificationReadView.as_view(), name="notification-read"),
    path("<int:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    path("device-tokens/", DeviceTokenRegisterView.as_view(), name="device-token-register"),
]
