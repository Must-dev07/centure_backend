"""Baby CRUD, scoped by role:
- parent: only their own babies (create allowed)
- doctor: only babies assigned to them (read + limited update)
- admin: everything

Doctor assignment (Section 3) is a real request/accept workflow, not a
free-form field edit: parents request a doctor (DoctorAssignmentRequest,
pending), the doctor accepts or declines, and only acceptance changes
`Baby.assigned_doctor`. Admins bypass the request dance and assign/remove
doctors directly via PATCH; a doctor may remove *themselves* from a patient
the same way. See `BabyDetailView.perform_update` for the enforcement.
"""
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsParentOfBabyOrAssignedDoctorOrAdmin
from notifications.models import Notification
from notifications.utils import notify
from .models import Baby, DoctorAssignmentRequest, MedicalHistoryEntry
from .serializers import BabySerializer, DoctorAssignmentRequestSerializer, MedicalHistoryEntrySerializer


def babies_for(user):
    qs = Baby.objects.select_related("parent__user", "assigned_doctor__user").prefetch_related(
        "medical_history"
    )
    if user.role == "admin":
        return qs
    if user.role == "doctor":
        return qs.filter(assigned_doctor__user=user)
    return qs.filter(parent__user=user)


def doctor_requests_for(user):
    qs = DoctorAssignmentRequest.objects.select_related(
        "baby__parent__user", "doctor__user"
    )
    if user.role == "admin":
        return qs
    if user.role == "doctor":
        return qs.filter(doctor__user=user)
    return qs.filter(baby__parent__user=user)


class BabyListCreateView(generics.ListCreateAPIView):
    serializer_class = BabySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return babies_for(self.request.user).order_by("id")

    def perform_create(self, serializer):
        user = self.request.user
        if user.role != "parent":
            raise PermissionDenied("Only parents can register a baby.")
        serializer.save(parent=user.parent_profile)


class BabyDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BabySerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsParentOfBabyOrAssignedDoctorOrAdmin,
    ]

    def get_queryset(self):
        return babies_for(self.request.user)

    def perform_update(self, serializer):
        user = self.request.user
        core_fields = {"name", "birth_date", "weight_grams", "gender"}
        if user.role == "doctor" and core_fields & set(serializer.validated_data):
            raise PermissionDenied(
                "Doctors cannot edit a patient's registration details — "
                "add a medical history entry instead."
            )
        if "assigned_doctor" in serializer.validated_data:
            new_doctor = serializer.validated_data["assigned_doctor"]
            instance = serializer.instance
            is_admin = user.role == "admin"
            is_self_removal = (
                user.role == "doctor"
                and new_doctor is None
                and instance.assigned_doctor_id is not None
                and instance.assigned_doctor.user_id == user.id
            )
            if not (is_admin or is_self_removal):
                raise PermissionDenied(
                    "Doctor assignment changes go through a request (parent) "
                    "or an admin action — not a direct edit. A doctor may "
                    "only remove themselves from a patient."
                )
        serializer.save()

    def perform_destroy(self, instance):
        if self.request.user.role == "doctor":
            raise PermissionDenied("Doctors cannot delete patient records.")
        instance.delete()


class MedicalHistoryListCreateView(generics.ListCreateAPIView):
    """Append-only medical history. Doctors (assigned) and admins can append."""

    serializer_class = MedicalHistoryEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_baby(self):
        baby = generics.get_object_or_404(babies_for(self.request.user), pk=self.kwargs["baby_id"])
        return baby

    def get_queryset(self):
        return MedicalHistoryEntry.objects.filter(baby=self.get_baby())

    def perform_create(self, serializer):
        user = self.request.user
        baby = self.get_baby()  # 404 first if the baby is out of scope (no data leak)
        if user.role not in ("doctor", "admin"):
            raise PermissionDenied("Only doctors or admins can add medical history.")
        doctor = getattr(user, "doctor_profile", None)
        serializer.save(baby=baby, recorded_by=doctor)


class DoctorRequestListCreateView(generics.ListCreateAPIView):
    """Nested under a baby: history of doctor requests for that baby, and
    where a parent creates a new one."""

    serializer_class = DoctorAssignmentRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_baby(self):
        return generics.get_object_or_404(babies_for(self.request.user), pk=self.kwargs["baby_id"])

    def get_queryset(self):
        return DoctorAssignmentRequest.objects.filter(baby=self.get_baby())

    def perform_create(self, serializer):
        user = self.request.user
        baby = self.get_baby()
        if user.role == "parent" and baby.parent.user_id != user.id:
            raise PermissionDenied("Not your baby.")
        if user.role not in ("parent", "admin"):
            raise PermissionDenied("Only the parent or an admin can request a doctor.")
        if DoctorAssignmentRequest.objects.filter(baby=baby, status=DoctorAssignmentRequest.Status.PENDING).exists():
            raise ValidationError("A doctor request is already pending for this baby.")
        request_obj = serializer.save(
            baby=baby, requested_by=user, status=DoctorAssignmentRequest.Status.PENDING
        )
        notify(
            request_obj.doctor.user,
            "New patient request",
            f"{baby.parent.user.get_full_name()} requested you as {baby.name}'s doctor.",
            category=Notification.Category.MEDICAL,
        )


class DoctorRequestInboxView(generics.ListAPIView):
    """Top-level inbox: doctors see requests addressed to them, parents see
    requests for their own babies, admins see everything. Filter with
    ?status=pending to build a doctor's "pending requests" screen."""

    serializer_class = DoctorAssignmentRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = doctor_requests_for(self.request.user).order_by("-created_at")
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class _DoctorRequestActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_pending_request(self, pk):
        req = generics.get_object_or_404(DoctorAssignmentRequest, pk=pk)
        if req.status != DoctorAssignmentRequest.Status.PENDING:
            raise ValidationError("This request is no longer pending.")
        return req


class DoctorRequestAcceptView(_DoctorRequestActionView):
    def post(self, request, pk):
        req = self.get_pending_request(pk)
        if not (request.user.role == "doctor" and req.doctor.user_id == request.user.id):
            raise PermissionDenied("Only the requested doctor can accept this.")
        req.status = DoctorAssignmentRequest.Status.ACCEPTED
        req.responded_at = timezone.now()
        req.save(update_fields=["status", "responded_at"])
        req.baby.assigned_doctor = req.doctor
        req.baby.save(update_fields=["assigned_doctor"])
        # A baby has one active doctor: superseded pending requests are closed.
        DoctorAssignmentRequest.objects.filter(
            baby=req.baby, status=DoctorAssignmentRequest.Status.PENDING
        ).exclude(pk=req.pk).update(
            status=DoctorAssignmentRequest.Status.DECLINED, responded_at=timezone.now()
        )
        notify(
            req.baby.parent.user,
            "Doctor request accepted",
            f"Dr. {req.doctor.user.get_full_name()} accepted your request for {req.baby.name}.",
            category=Notification.Category.MEDICAL,
        )
        return Response(DoctorAssignmentRequestSerializer(req).data)


class DoctorRequestDeclineView(_DoctorRequestActionView):
    def post(self, request, pk):
        req = self.get_pending_request(pk)
        if not (request.user.role == "doctor" and req.doctor.user_id == request.user.id):
            raise PermissionDenied("Only the requested doctor can decline this.")
        req.status = DoctorAssignmentRequest.Status.DECLINED
        req.responded_at = timezone.now()
        req.save(update_fields=["status", "responded_at"])
        notify(
            req.baby.parent.user,
            "Doctor request declined",
            f"Dr. {req.doctor.user.get_full_name()} declined your request for {req.baby.name}.",
            category=Notification.Category.MEDICAL,
        )
        return Response(DoctorAssignmentRequestSerializer(req).data)


class DoctorRequestCancelView(_DoctorRequestActionView):
    """The requester (or an admin) can withdraw a still-pending request."""

    def post(self, request, pk):
        req = self.get_pending_request(pk)
        if not (req.requested_by_id == request.user.id or request.user.role == "admin"):
            raise PermissionDenied("Only the requester or an admin can cancel this.")
        req.status = DoctorAssignmentRequest.Status.CANCELLED
        req.responded_at = timezone.now()
        req.save(update_fields=["status", "responded_at"])
        return Response(DoctorAssignmentRequestSerializer(req).data)
