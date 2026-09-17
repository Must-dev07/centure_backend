"""Celery tasks for the analysis app: non-critical rule pass + no-data watchdog."""
from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def evaluate_non_critical_rules(measurement_id: int) -> int:
    """Runs all non-critical rules for a measurement (queued at ingest time)."""
    from measurements.models import Measurement
    from analysis.rules import run_rules

    try:
        m = Measurement.objects.select_related("baby", "bracelet").get(id=measurement_id)
    except Measurement.DoesNotExist:
        return 0
    return len(run_rules(m, non_critical_only=True))


@shared_task
def detect_no_data() -> int:
    """Celery-beat task: raises a NO_DATA alert for every actively-paired
    bracelet that has not been seen for NO_DATA_MINUTES."""
    from alerts.models import Alert
    from bracelets.models import Bracelet
    from notifications.tasks import dispatch_alert_notifications

    cutoff = timezone.now() - timezone.timedelta(
        minutes=settings.ANALYSIS_THRESHOLDS["NO_DATA_MINUTES"]
    )
    stale = Bracelet.objects.filter(
        baby__isnull=False, status=Bracelet.Status.ACTIVE
    ).filter(last_seen_at__lt=cutoff) | Bracelet.objects.filter(
        baby__isnull=False, status=Bracelet.Status.ACTIVE, last_seen_at__isnull=True
    )
    count = 0
    for bracelet in stale.select_related("baby").distinct():
        if Alert.objects.filter(
            baby_id=bracelet.baby_id, type=Alert.Type.NO_DATA, resolved_at__isnull=True
        ).exists():
            continue
        alert = Alert.objects.create(
            baby_id=bracelet.baby_id,
            bracelet=bracelet,
            type=Alert.Type.NO_DATA,
            severity=Alert.Severity.WARNING,
            message=(
                "No data received from the bracelet for "
                f"{settings.ANALYSIS_THRESHOLDS['NO_DATA_MINUTES']:.0f} minutes — "
                "please check the device and connection."
            ),
            triggered_at=timezone.now(),
        )
        dispatch_alert_notifications.delay(alert.id)
        count += 1
    return count
