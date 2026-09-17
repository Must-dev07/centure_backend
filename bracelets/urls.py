from django.urls import path

from .views import (
    BraceletDetailView,
    BraceletListCreateView,
    PairingHistoryView,
    PairView,
    UnpairView,
)

urlpatterns = [
    path("", BraceletListCreateView.as_view(), name="bracelet-list"),
    path("<int:pk>/", BraceletDetailView.as_view(), name="bracelet-detail"),
    path("<int:pk>/pair/", PairView.as_view(), name="bracelet-pair"),
    path("<int:pk>/unpair/", UnpairView.as_view(), name="bracelet-unpair"),
    path("<int:pk>/pairings/", PairingHistoryView.as_view(), name="bracelet-pairings"),
]
