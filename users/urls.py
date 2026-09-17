from django.urls import path

from .views import (
    DoctorDetailView,
    DoctorListView,
    MeDeactivateView,
    MeView,
    ParentDetailView,
    ParentListView,
    UserListView,
)

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/deactivate/", MeDeactivateView.as_view(), name="me-deactivate"),
    path("users/", UserListView.as_view(), name="user-list"),
    path("doctors/", DoctorListView.as_view(), name="doctor-list"),
    path("doctors/<int:pk>/", DoctorDetailView.as_view(), name="doctor-detail"),
    path("parents/", ParentListView.as_view(), name="parent-list"),
    path("parents/<int:pk>/", ParentDetailView.as_view(), name="parent-detail"),
]
