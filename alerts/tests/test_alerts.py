"""Alert list/filter/acknowledge + notification fan-out tests."""
import pytest
from django.utils import timezone

from alerts.models import Alert
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def make_alert(baby, bracelet, **kw):
    defaults = dict(
        baby=baby, bracelet=bracelet, type=Alert.Type.HIGH_TEMP,
        severity=Alert.Severity.CRITICAL, message="Temp flagged", triggered_at=timezone.now(),
    )
    defaults.update(kw)
    return Alert.objects.create(**defaults)


def test_parent_lists_own_alerts_with_disclaimer(parent_client, baby, bracelet):
    make_alert(baby, bracelet)
    resp = parent_client.get("/api/v1/alerts/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert "not a medical diagnosis" in resp.data["results"][0]["disclaimer"]


def test_status_filter(parent_client, baby, bracelet):
    make_alert(baby, bracelet)
    make_alert(baby, bracelet, type=Alert.Type.LOW_HR, resolved_at=timezone.now())
    resp = parent_client.get("/api/v1/alerts/", {"status": "active"})
    assert resp.data["count"] == 1
    resp = parent_client.get("/api/v1/alerts/", {"status": "resolved"})
    assert resp.data["count"] == 1


def test_acknowledge_vitals_alert_does_not_resolve_it(parent_client, parent, baby, bracelet):
    # High-temp is vitals-based: a parent acknowledging it means "I've seen
    # this", not "it's medically resolved" — it must stay open.
    alert = make_alert(baby, bracelet)
    resp = parent_client.post(f"/api/v1/alerts/{alert.id}/acknowledge/")
    assert resp.status_code == 200
    assert resp.data["auto_resolves_on_acknowledge"] is False
    alert.refresh_from_db()
    assert alert.acknowledged_by == parent.user
    assert alert.resolved_at is None


def test_acknowledge_non_persistent_alert_resolves_it(parent_client, parent, baby, bracelet):
    # battery_low is a one-off device event with no future signal that would
    # clear it on its own — acknowledging IS resolving.
    alert = make_alert(baby, bracelet, type=Alert.Type.BATTERY_LOW, severity=Alert.Severity.INFO)
    resp = parent_client.post(f"/api/v1/alerts/{alert.id}/acknowledge/")
    assert resp.status_code == 200
    assert resp.data["auto_resolves_on_acknowledge"] is True
    alert.refresh_from_db()
    assert alert.resolved_at is not None
    assert alert.resolved_by == parent.user


def test_parent_cannot_resolve_vitals_alert(parent_client, baby, bracelet):
    alert = make_alert(baby, bracelet)
    resp = parent_client.post(f"/api/v1/alerts/{alert.id}/resolve/")
    assert resp.status_code == 403
    alert.refresh_from_db()
    assert alert.resolved_at is None


def test_assigned_doctor_can_resolve_vitals_alert(doctor, doctor_client, baby, bracelet):
    alert = make_alert(baby, bracelet)
    resp = doctor_client.post(f"/api/v1/alerts/{alert.id}/resolve/")
    assert resp.status_code == 200
    alert.refresh_from_db()
    assert alert.resolved_at is not None
    assert alert.resolved_by == doctor.user
    # Resolving implies review — acknowledged gets backfilled too.
    assert alert.acknowledged_by == doctor.user


def test_cannot_resolve_an_already_resolved_alert(doctor_client, baby, bracelet):
    alert = make_alert(baby, bracelet, resolved_at=timezone.now())
    resp = doctor_client.post(f"/api/v1/alerts/{alert.id}/resolve/")
    assert resp.status_code == 400


def test_acknowledged_by_name_populated(parent_client, parent, baby, bracelet):
    parent.user.first_name, parent.user.last_name = "Marie", "Dupont"
    parent.user.save()
    alert = make_alert(baby, bracelet)
    parent_client.post(f"/api/v1/alerts/{alert.id}/acknowledge/")
    resp = parent_client.get(f"/api/v1/alerts/{alert.id}/")
    assert resp.data["acknowledged_by_name"] == "Marie Dupont"


def test_date_range_filter(parent_client, baby, bracelet):
    old = make_alert(baby, bracelet, triggered_at=timezone.now() - timezone.timedelta(days=10))
    recent = make_alert(baby, bracelet, type=Alert.Type.LOW_HR)
    since = (timezone.now() - timezone.timedelta(days=1)).isoformat()
    resp = parent_client.get("/api/v1/alerts/", {"from": since})
    ids = {a["id"] for a in resp.data["results"]}
    assert recent.id in ids
    assert old.id not in ids


def test_foreign_alert_invisible(doctor_client, baby, bracelet):
    # doctor fixture is NOT this baby's doctor in this test setup? It is —
    # so create a baby with a different doctor to assert isolation.
    from tests.factories import BabyFactory, BraceletFactory

    other_baby = BabyFactory()
    other_bracelet = BraceletFactory()
    alert = make_alert(other_baby, other_bracelet)
    resp = doctor_client.get(f"/api/v1/alerts/{alert.id}/")
    assert resp.status_code == 404


def test_ble_lost_report(parent_client, bracelet):
    resp = parent_client.post(
        "/api/v1/alerts/report-ble-lost/", {"bracelet_id": bracelet.id}, format="json"
    )
    assert resp.status_code == 201
    assert Alert.objects.filter(type="ble_lost").count() == 1
    # Duplicate report while open → no second alert
    resp = parent_client.post(
        "/api/v1/alerts/report-ble-lost/", {"bracelet_id": bracelet.id}, format="json"
    )
    assert resp.status_code == 200
    assert Alert.objects.filter(type="ble_lost").count() == 1


def test_notification_fanout_parent_and_doctor(baby, bracelet):
    """Celery eager mode: dispatch runs inline. FCM is unconfigured in tests so
    notifications are recorded with status=failed, but rows exist for both
    the parent and the assigned doctor (severity=critical)."""
    from analysis.rules import run_rules
    from tests.factories import MeasurementFactory

    m = MeasurementFactory(baby=baby, bracelet=bracelet, spo2=85.0)
    run_rules(m)
    users = set(Notification.objects.values_list("user_id", flat=True))
    assert baby.parent.user_id in users
    assert baby.assigned_doctor.user_id in users
    body = Notification.objects.first().body
    assert "not a diagnosis" in body


def test_search_and_ordering(parent_client, baby, bracelet):
    make_alert(baby, bracelet, type=Alert.Type.LOW_OXYGEN, severity=Alert.Severity.WARNING)
    make_alert(baby, bracelet, type=Alert.Type.HIGH_HR, severity=Alert.Severity.CRITICAL)

    resp = parent_client.get("/api/v1/alerts/", {"search": "low_oxygen"})
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["type"] == "low_oxygen"

    resp = parent_client.get("/api/v1/alerts/", {"ordering": "severity"})
    assert resp.status_code == 200
