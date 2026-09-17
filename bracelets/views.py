"""Bracelet CRUD + pair/unpair actions with full history."""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import user_can_access_baby
from notifications.models import Notification
from notifications.utils import notify
from .models import Bracelet, Pairing
from .serializers import BraceletSerializer, PairingSerializer, PairRequestSerializer


def bracelets_for(user):
    qs = Bracelet.objects.select_related("baby")
    if user.role == "admin":
        return qs
    if user.role == "doctor":
        return qs.filter(baby__assigned_doctor__user=user)
    # Parents see bracelets paired with their babies + unassigned ones (to pair)
    return qs.filter(baby__parent__user=user) | qs.filter(baby__isnull=True)


class BraceletListCreateView(generics.ListCreateAPIView):
    serializer_class = BraceletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return bracelets_for(self.request.user).distinct().order_by("id")

    def perform_create(self, serializer):
        # Any authenticated user can register a bracelet they own (serial from box).
        serializer.save()


class BraceletDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BraceletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return bracelets_for(self.request.user).distinct()

    def perform_destroy(self, instance):
        if self.request.user.role != "admin":
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only admins can delete bracelets.")
        instance.delete()


class PairView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        bracelet = generics.get_object_or_404(
            bracelets_for(request.user).distinct(), pk=pk
        )
        serializer = PairRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        baby = serializer.validated_data["baby"]
        if not user_can_access_baby(request.user, baby):
            return Response({"detail": "You cannot pair with this baby."}, status=403)
        pairing = bracelet.pair_with(baby)
        notify(
            baby.parent.user,
            "Bracelet paired",
            f"{bracelet.serial_number} is now paired with {baby.name}.",
            category=Notification.Category.BRACELET,
        )
        if baby.assigned_doctor:
            notify(
                baby.assigned_doctor.user,
                "Bracelet paired",
                f"{baby.name}'s bracelet ({bracelet.serial_number}) is now active.",
                category=Notification.Category.BRACELET,
            )
        return Response(PairingSerializer(pairing).data, status=status.HTTP_201_CREATED)


class UnpairView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        bracelet = generics.get_object_or_404(
            bracelets_for(request.user).distinct(), pk=pk
        )
        if bracelet.baby and not user_can_access_baby(request.user, bracelet.baby):
            return Response({"detail": "Forbidden."}, status=403)
        baby = bracelet.baby
        bracelet.unpair()
        if baby:
            notify(
                baby.parent.user,
                "Bracelet disconnected",
                f"{bracelet.serial_number} was unpaired from {baby.name}.",
                category=Notification.Category.BRACELET,
            )
        return Response({"detail": "Unpaired."})


class PairingHistoryView(generics.ListAPIView):
    """Pairing history for a bracelet the caller can access — parent (own
    baby), assigned doctor, or admin. Previously gated by a blanket
    IsDoctorOrAdmin check, which let *any* doctor see *any* baby's pairing
    history and excluded parents entirely; now scoped through the same
    bracelets_for() every other bracelet view uses."""

    serializer_class = PairingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        bracelet = generics.get_object_or_404(
            bracelets_for(self.request.user).distinct(), pk=self.kwargs["pk"]
        )
        return Pairing.objects.filter(bracelet=bracelet).select_related("baby")
