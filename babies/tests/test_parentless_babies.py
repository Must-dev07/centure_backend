"""A baby enrolled before its parent accepted the invitation has parent=None.
Every existing path that used to assume a parent must keep working."""
import pytest
from django.utils import timezone

from alerts.models import Alert
from babies.models import DoctorAssignmentRequest
from notifications.models import Notification
from notifications.tasks import dispatch_alert_notifications
from tests.factories import BabyFactory, beltFactory, DoctorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def orphan(doctor):
    return BabyFactory(parent=None, assigned_doctor=doctor)


def test_detail_serializes_without_parent(orphan, doctor_client):
    resp = doctor_client.get(f"/api/v1/babies/{orphan.id}/")
    assert resp.status_code == 200
    assert resp.data["parent"] is None
    assert resp.data["parent_name"] == ""


def test_pair_and_unpair_without_parent(orphan, doctor, doctor_client):
    belt = beltFactory()
    resp = doctor_client.post(
        f"/api/v1/belts/{belt.id}/pair/", {"baby_id": orphan.id}, format="json"
    )
    assert resp.status_code == 201
    # The doctor is still notified; there is no parent to notify.
    assert Notification.objects.filter(user=doctor.user, title="belt paired").exists()
    assert Notification.objects.filter(title="belt paired").count() == 1

    resp = doctor_client.post(f"/api/v1/belts/{belt.id}/unpair/")
    assert resp.status_code == 200
    assert not Notification.objects.filter(title="belt disconnected").exists()


def test_parent_cannot_pair_baby_without_parent(orphan, parent_client):
    belt = beltFactory()
    resp = parent_client.post(
        f"/api/v1/belts/{belt.id}/pair/", {"baby_id": orphan.id}, format="json"
    )
    assert resp.status_code == 403


def test_alert_dispatch_without_parent(orphan, doctor):
    alert = Alert.objects.create(
        baby=orphan, type=Alert.Type.HIGH_TEMP, severity=Alert.Severity.CRITICAL,
        message="Temp flagged", triggered_at=timezone.now(),
    )
    dispatch_alert_notifications(alert.id)  # must not raise
    notified = set(Notification.objects.filter(alert=alert).values_list("user_id", flat=True))
    assert notified == {doctor.user_id}


def test_alert_dispatch_without_parent_or_doctor():
    baby = BabyFactory(parent=None, assigned_doctor=None)
    alert = Alert.objects.create(
        baby=baby, type=Alert.Type.BATTERY_LOW, severity=Alert.Severity.INFO,
        message="Battery low", triggered_at=timezone.now(),
    )
    assert dispatch_alert_notifications(alert.id) == 0
    assert not Notification.objects.filter(alert=alert).exists()


def test_doctor_request_flow_without_parent(admin_client):
    baby = BabyFactory(parent=None, assigned_doctor=None)
    target = DoctorFactory()
    resp = admin_client.post(
        f"/api/v1/babies/{baby.id}/doctor-requests/", {"doctor": target.id}, format="json"
    )
    assert resp.status_code == 201
    note = Notification.objects.get(user=target.user, title="New patient request")
    assert baby.name in note.body

    from rest_framework.test import APIClient

    target_client = APIClient()
    target_client.force_authenticate(user=target.user)
    resp = target_client.post(f"/api/v1/babies/doctor-requests/{resp.data['id']}/accept/")
    assert resp.status_code == 200
    baby.refresh_from_db()
    assert baby.assigned_doctor_id == target.id


def test_doctor_request_decline_without_parent(admin_client):
    baby = BabyFactory(parent=None, assigned_doctor=None)
    target = DoctorFactory()
    request_id = admin_client.post(
        f"/api/v1/babies/{baby.id}/doctor-requests/", {"doctor": target.id}, format="json"
    ).data["id"]

    from rest_framework.test import APIClient

    target_client = APIClient()
    target_client.force_authenticate(user=target.user)
    resp = target_client.post(f"/api/v1/babies/doctor-requests/{request_id}/decline/")
    assert resp.status_code == 200
    assert DoctorAssignmentRequest.objects.get(pk=request_id).status == "declined"
