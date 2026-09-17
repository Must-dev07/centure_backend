"""Celery pipeline: alert -> resolve targets -> create Notification rows -> dispatch."""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Which severities notify the assigned doctor (parents are always notified).
DOCTOR_SEVERITIES = ("warning", "critical")


@shared_task
def dispatch_alert_notifications(alert_id: int) -> int:
    from alerts.models import Alert
    from notifications.channels import CHANNELS
    from notifications.models import Notification

    try:
        alert = Alert.objects.select_related(
            "baby__parent__user", "baby__assigned_doctor__user"
        ).get(id=alert_id)
    except Alert.DoesNotExist:
        return 0

    targets = [alert.baby.parent.user]
    doctor = alert.baby.assigned_doctor
    if doctor and alert.severity in DOCTOR_SEVERITIES:
        targets.append(doctor.user)

    # Non-diagnostic wording enforced at the source (Section 0 rule 10).
    title = f"Reading flagged: {alert.get_type_display().replace('_', ' ')}"
    body = f"{alert.baby.name}: {alert.message} This is not a diagnosis."

    sent = 0
    for user in targets:
        notification = Notification.objects.create(
            user=user, alert=alert, category=Notification.Category.ALERT,
            channel=Notification.Channel.PUSH,
            title=title[:128], body=body[:512],
        )
        channel = CHANNELS.get(notification.channel)
        ok = False
        if channel:
            try:
                ok = channel.send(notification)
            except Exception:
                logger.exception("channel send failed")
        notification.status = Notification.Status.SENT if ok else Notification.Status.FAILED
        notification.sent_at = timezone.now() if ok else None
        notification.save(update_fields=["status", "sent_at"])
        sent += int(ok)
    return sent
