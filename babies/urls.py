from django.urls import path

from .views import (
    BabyDetailView,
    BabyListCreateView,
    DoctorRequestAcceptView,
    DoctorRequestCancelView,
    DoctorRequestDeclineView,
    DoctorRequestInboxView,
    DoctorRequestListCreateView,
    MedicalHistoryListCreateView,
)

urlpatterns = [
    path("", BabyListCreateView.as_view(), name="baby-list"),
    path("doctor-requests/", DoctorRequestInboxView.as_view(), name="doctor-request-inbox"),
    path("doctor-requests/<int:pk>/accept/", DoctorRequestAcceptView.as_view(), name="doctor-request-accept"),
    path("doctor-requests/<int:pk>/decline/", DoctorRequestDeclineView.as_view(), name="doctor-request-decline"),
    path("doctor-requests/<int:pk>/cancel/", DoctorRequestCancelView.as_view(), name="doctor-request-cancel"),
    path("<int:pk>/", BabyDetailView.as_view(), name="baby-detail"),
    path("<int:baby_id>/medical-history/", MedicalHistoryListCreateView.as_view(), name="baby-medical-history"),
    path("<int:baby_id>/doctor-requests/", DoctorRequestListCreateView.as_view(), name="baby-doctor-requests"),
]
