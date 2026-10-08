"""belt CRUD + pair/unpair actions with full history."""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import user_can_access_baby
from notifications.models import Notification
from notifications.utils import notify
from .models import belt, Pairing
from .serializers import beltSerializer, PairingSerializer, PairRequestSerializer


def belts_for(user):
    qs = belt.objects.select_related("baby")
    if user.role == "admin":
        return qs
    if user.role == "doctor":
        return qs.filter(baby__assigned_doctor__user=user)
    # Parents see belts paired with their babies + unassigned ones (to pair)
    return qs.filter(baby__parent__user=user) | qs.filter(baby__isnull=True)


def pairable_belts_for(user):
    """belts a user may pair (REFONTE §3.5: owning parent, assigned doctor,
    or admin). Like parents, an assigned doctor can pair a not-yet-assigned
    belt (e.g. at the hospital); the listing scope above is unchanged."""
    qs = belts_for(user)
    if user.role == "doctor":
        qs = qs | belt.objects.select_related("baby").filter(baby__isnull=True)
    return qs


class beltListCreateView(generics.ListCreateAPIView):
    serializer_class = beltSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # ?serial_number= looks a belt up before pairing it (the mobile app
        # registers by serial and falls back to this when it already exists),
        # so it searches what the caller may pair: for an assigned doctor that
        # includes not-yet-assigned belts the plain listing leaves out.
        serial = self.request.query_params.get("serial_number")
        if serial:
            return (
                pairable_belts_for(self.request.user)
                .filter(serial_number=serial)
                .distinct()
                .order_by("id")
            )
        return belts_for(self.request.user).distinct().order_by("id")

    def perform_create(self, serializer):
        # Any authenticated user can register a belt they own (serial from box).
        serializer.save()


class beltDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = beltSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return belts_for(self.request.user).distinct()

    def perform_destroy(self, instance):
        if self.request.user.role != "admin":
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Only admins can delete belts.")
        instance.delete()


class PairView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        belt = generics.get_object_or_404(
            pairable_belts_for(request.user).distinct(), pk=pk
        )
        serializer = PairRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        baby = serializer.validated_data["baby"]
        if not user_can_access_baby(request.user, baby):
            return Response({"detail": "You cannot pair with this baby."}, status=403)
        pairing = belt.pair_with(baby)
        if baby.parent_id is not None:  # no parent yet until the invitation is accepted
            notify(
                baby.parent.user,
                "belt paired",
                f"{belt.serial_number} is now paired with {baby.name}.",
                category=Notification.Category.belt,
            )
        if baby.assigned_doctor:
            notify(
                baby.assigned_doctor.user,
                "belt paired",
                f"{baby.name}'s belt ({belt.serial_number}) is now active.",
                category=Notification.Category.belt,
            )
        return Response(PairingSerializer(pairing).data, status=status.HTTP_201_CREATED)


class UnpairView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        belt = generics.get_object_or_404(
            belts_for(request.user).distinct(), pk=pk
        )
        if belt.baby and not user_can_access_baby(request.user, belt.baby):
            return Response({"detail": "Forbidden."}, status=403)
        baby = belt.baby
        belt.unpair()
        if baby and baby.parent_id is not None:
            notify(
                baby.parent.user,
                "belt disconnected",
                f"{belt.serial_number} was unpaired from {baby.name}.",
                category=Notification.Category.belt,
            )
        return Response({"detail": "Unpaired."})


class PairingHistoryView(generics.ListAPIView):
    """Pairing history for a belt the caller can access — parent (own
    baby), assigned doctor, or admin. Previously gated by a blanket
    IsDoctorOrAdmin check, which let *any* doctor see *any* baby's pairing
    history and excluded parents entirely; now scoped through the same
    belts_for() every other belt view uses."""

    serializer_class = PairingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        belt = generics.get_object_or_404(
            belts_for(self.request.user).distinct(), pk=self.kwargs["pk"]
        )
        return Pairing.objects.filter(belt=belt).select_related("baby")
