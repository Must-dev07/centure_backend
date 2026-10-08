from django.urls import path

from .views import (
    beltDetailView,
    beltListCreateView,
    PairingHistoryView,
    PairView,
    UnpairView,
)

urlpatterns = [
    path("", beltListCreateView.as_view(), name="belt-list"),
    path("<int:pk>/", beltDetailView.as_view(), name="belt-detail"),
    path("<int:pk>/pair/", PairView.as_view(), name="belt-pair"),
    path("<int:pk>/unpair/", UnpairView.as_view(), name="belt-unpair"),
    path("<int:pk>/pairings/", PairingHistoryView.as_view(), name="belt-pairings"),
]
