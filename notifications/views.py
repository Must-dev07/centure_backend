"""User-scoped notification list, mark-read, and FCM device-token registration."""
from django.utils import timezone
from rest_framework import filters, generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeviceToken, Notification, NotificationPreference
from .serializers import DeviceTokenSerializer, NotificationSerializer


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs


class NotificationDetailView(generics.DestroyAPIView):
    """Delete a single notification (Section 9)."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = generics.get_object_or_404(
            Notification.objects.filter(user=request.user), pk=pk
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.status = Notification.Status.READ
            notification.save(update_fields=["read_at", "status"])
        return Response(NotificationSerializer(notification).data)


class NotificationReadAllView(APIView):
    """Mark every unread notification belonging to the current user as read."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            user=request.user, read_at__isnull=True
        ).update(read_at=timezone.now(), status=Notification.Status.READ)
        return Response({"marked_read": updated})


class NotificationPreferencesView(APIView):
    """Section 11: mute bracelet/medical/system notifications. `alert` is
    deliberately not accepted here — see NotificationPreference's docstring.
    GET/PATCH body shape: {"bracelet": bool, "medical": bool, "system": bool}
    (a category absent from the response means "enabled", the default)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(self._current(request.user))

    def patch(self, request):
        for category, enabled in request.data.items():
            if category not in NotificationPreference.MutableCategory.values:
                continue
            NotificationPreference.objects.update_or_create(
                user=request.user, category=category, defaults={"enabled": bool(enabled)}
            )
        return Response(self._current(request.user))

    def _current(self, user):
        muted = set(
            NotificationPreference.objects.filter(user=user, enabled=False)
            .values_list("category", flat=True)
        )
        return {c: c not in muted for c in NotificationPreference.MutableCategory.values}


class DeviceTokenRegisterView(APIView):
    """Mobile app registers its FCM token after login; idempotent upsert."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj, _created = DeviceToken.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "user": request.user,
                "platform": serializer.validated_data.get("platform", "android"),
            },
        )
        return Response(DeviceTokenSerializer(obj).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        token = request.data.get("token", "")
        DeviceToken.objects.filter(user=request.user, token=token).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
