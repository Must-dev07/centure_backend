"""Synchronous notification creation/dispatch, for low-volume user-triggered
events (doctor assignment requests, acceptances, etc). The alert pipeline
uses its own Celery task (tasks.py) since ingest is high-throughput and must
not block the measurements endpoint; this helper is for the opposite case —
one-off events that already happen inside a normal request/response cycle.
"""
from django.utils import timezone

from .channels import CHANNELS
from .models import Notification, NotificationPreference


def is_category_enabled(user, category: str) -> bool:
    """Alert notifications are never gated — vitals/device alerts are
    safety-relevant. Every other category defaults to enabled unless the
    user has explicitly muted it (Section 11)."""
    if category == Notification.Category.ALERT:
        return True
    return not NotificationPreference.objects.filter(
        user=user, category=category, enabled=False
    ).exists()


def notify(user, title: str, body: str, *, category: str = Notification.Category.SYSTEM, alert=None) -> Notification | None:
    if not is_category_enabled(user, category):
        return None
    notification = Notification.objects.create(
        user=user,
        alert=alert,
        category=category,
        channel=Notification.Channel.PUSH,
        title=title[:128],
        body=body[:512],
    )
    channel = CHANNELS.get(notification.channel)
    ok = False
    if channel:
        try:
            ok = channel.send(notification)
        except Exception:
            ok = False
    notification.status = Notification.Status.SENT if ok else Notification.Status.FAILED
    notification.sent_at = timezone.now() if ok else None
    notification.save(update_fields=["status", "sent_at"])
    return notification
