"""Role-based permission classes shared across apps.

Roles are enforced server-side from the DB user record — never from client
claims (Section 7 checklist).
"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == "admin")


class IsDoctor(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == "doctor")


class IsParent(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.role == "parent")


class IsDoctorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated and request.user.role in ("doctor", "admin")
        )


def user_can_access_baby(user, baby) -> bool:
    """Central baby-scoped access rule used by object permissions below."""
    if user.role == "admin":
        return True
    if user.role == "parent":
        return baby.parent.user_id == user.id
    if user.role == "doctor":
        return baby.assigned_doctor is not None and baby.assigned_doctor.user_id == user.id
    return False


class IsParentOfBabyOrAssignedDoctorOrAdmin(BasePermission):
    """Object-level guard for any object exposing `.baby` or being a Baby."""

    def has_object_permission(self, request, view, obj):
        baby = getattr(obj, "baby", obj)
        return user_can_access_baby(request.user, baby)
