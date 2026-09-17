"""Doctor/Parent profile endpoints + admin user listing for the dashboard."""
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.models import Session
from common.permissions import IsAdmin
from .models import Doctor, Parent, User
from .serializers import DoctorSerializer, ParentSerializer, UserSummarySerializer


class IsSelfOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.role == "admin" or obj.user_id == request.user.id


class DoctorDetailView(generics.RetrieveUpdateAPIView):
    queryset = Doctor.objects.select_related("user")
    serializer_class = DoctorSerializer
    permission_classes = [permissions.IsAuthenticated, IsSelfOrAdmin]


class ParentDetailView(generics.RetrieveUpdateAPIView):
    queryset = Parent.objects.select_related("user")
    serializer_class = ParentSerializer
    permission_classes = [permissions.IsAuthenticated, IsSelfOrAdmin]


class DoctorListView(generics.ListAPIView):
    """Used by admin (dashboard user management) and to assign doctors."""

    queryset = Doctor.objects.select_related("user").order_by("id")
    serializer_class = DoctorSerializer
    permission_classes = [permissions.IsAuthenticated]


class ParentListView(generics.ListAPIView):
    """Admin-only: full parent list for the dashboard Parents page."""

    queryset = Parent.objects.select_related("user").order_by("id")
    serializer_class = ParentSerializer
    permission_classes = [IsAdmin]


class UserListView(generics.ListAPIView):
    """Admin-only: full user list for the dashboard Users page."""

    queryset = User.objects.order_by("id")
    serializer_class = UserSummarySerializer
    permission_classes = [IsAdmin]


class MeView(generics.RetrieveUpdateAPIView):
    """Current user's own summary. PATCH lets any authenticated user (parent,
    doctor, admin) edit their own name/phone -- the fields UserSummarySerializer
    exposes as writable. Doctors/parents additionally have DoctorDetailView /
    ParentDetailView for role-specific fields (specialty, address, etc.)."""

    serializer_class = UserSummarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class MeDeactivateView(APIView):
    """Section 11 "Delete account": soft-deletes (deactivates) the current
    user. Requires the current password as confirmation — this is
    irreversible from the user's side (only an admin can reactivate), so we
    don't accept it on a bare POST with no re-auth. Every session is revoked
    immediately; LoginView already rejects inactive users, so this alone
    blocks all future access without cascade-deleting medical records that
    other people (doctors, the child themselves later) may still need."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        password = request.data.get("password", "")
        if not password or not request.user.check_password(password):
            raise ValidationError({"password": "Incorrect password."})
        user = request.user
        user.is_active = False
        user.save(update_fields=["is_active"])
        Session.objects.filter(user=user, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        return Response({"detail": "Account deactivated."}, status=status.HTTP_200_OK)
