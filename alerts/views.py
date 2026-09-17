"""Alert list/acknowledge/resolve + BLE-lost reporting endpoint.

Acknowledge vs resolve (Section 8): anyone with access can acknowledge (it's
just "I've seen this"). For one-off device/connectivity alerts that's the
same as resolving — there's no future signal that would clear them on its
own. For vitals-based alerts, only a doctor or admin can resolve, since
resolving asserts the underlying concern is actually handled, not just seen.
"""
from django.utils import timezone
from rest_framework import filters, generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from babies.views import babies_for
from common.permissions import user_can_access_baby
from notifications.tasks import dispatch_alert_notifications
from .models import Alert
from .serializers import AlertSerializer, BleLostReportSerializer


class AlertListView(generics.ListAPIView):
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["baby__name", "type", "message"]
    ordering_fields = ["triggered_at", "severity", "resolved_at"]
    ordering = ["-triggered_at"]

    def get_queryset(self):
        qs = Alert.objects.filter(baby__in=babies_for(self.request.user)).select_related(
            "baby", "bracelet"
        )
        baby_id = self.request.query_params.get("baby_id")
        if baby_id:
            qs = qs.filter(baby_id=baby_id)
        status_param = self.request.query_params.get("status")
        if status_param == "active":
            qs = qs.filter(resolved_at__isnull=True)
        elif status_param == "resolved":
            qs = qs.filter(resolved_at__isnull=False)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        alert_type = self.request.query_params.get("type")
        if alert_type:
            qs = qs.filter(type=alert_type)
        date_from = self.request.query_params.get("from")
        if date_from:
            qs = qs.filter(triggered_at__gte=date_from)
        date_to = self.request.query_params.get("to")
        if date_to:
            qs = qs.filter(triggered_at__lte=date_to)
        return qs


class AlertDetailView(generics.RetrieveAPIView):
    serializer_class = AlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Alert.objects.filter(baby__in=babies_for(self.request.user))


class AlertAcknowledgeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        alert = generics.get_object_or_404(
            Alert.objects.filter(baby__in=babies_for(request.user)), pk=pk
        )
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        update_fields = ["acknowledged_by", "acknowledged_at"]
        if alert.resolved_at is None and alert.auto_resolves_on_acknowledge:
            alert.resolved_at = timezone.now()
            alert.resolved_by = request.user
            update_fields += ["resolved_at", "resolved_by"]
        alert.save(update_fields=update_fields)
        return Response(AlertSerializer(alert).data)


class AlertResolveView(APIView):
    """Doctor (assigned to the baby) or admin only. A parent can acknowledge
    but cannot assert a vitals-based alert is resolved."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        alert = generics.get_object_or_404(
            Alert.objects.filter(baby__in=babies_for(request.user)), pk=pk
        )
        if request.user.role not in ("doctor", "admin"):
            raise PermissionDenied("Only a doctor or admin can resolve an alert.")
        if alert.resolved_at is not None:
            raise ValidationError("This alert is already resolved.")
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        if alert.acknowledged_at is None:
            alert.acknowledged_by = request.user
            alert.acknowledged_at = timezone.now()
        alert.save(update_fields=["resolved_at", "resolved_by", "acknowledged_by", "acknowledged_at"])
        return Response(AlertSerializer(alert).data)


class ReportBleLostView(APIView):
    """The mobile app observes BLE link loss and reports it here (the backend
    itself cannot see the BLE link)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BleLostReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bracelet = serializer.validated_data["bracelet"]
        if bracelet.baby is None or not user_can_access_baby(request.user, bracelet.baby):
            return Response({"detail": "Forbidden."}, status=403)
        if Alert.objects.filter(
            baby_id=bracelet.baby_id, type=Alert.Type.BLE_LOST, resolved_at__isnull=True
        ).exists():
            return Response({"detail": "Already reported."}, status=200)
        alert = Alert.objects.create(
            baby_id=bracelet.baby_id,
            bracelet=bracelet,
            type=Alert.Type.BLE_LOST,
            severity=Alert.Severity.WARNING,
            message="Bluetooth connection to the bracelet was lost — live monitoring is interrupted.",
            triggered_at=timezone.now(),
        )
        dispatch_alert_notifications.delay(alert.id)
        return Response(AlertSerializer(alert).data, status=status.HTTP_201_CREATED)
