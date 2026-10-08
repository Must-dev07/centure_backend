"""Notification list/read + device token registration tests."""
import pytest
from django.utils import timezone

from notifications.models import DeviceToken, Notification

pytestmark = pytest.mark.django_db


def make_notification(user, **kw):
    defaults = dict(user=user, title="T", body="B", channel="push", status="sent",
                    sent_at=timezone.now())
    defaults.update(kw)
    return Notification.objects.create(**defaults)


def test_list_own_notifications_only(parent, parent_client, doctor):
    make_notification(parent.user)
    make_notification(doctor.user)
    resp = parent_client.get("/api/v1/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


def test_unread_filter_and_mark_read(parent, parent_client):
    n = make_notification(parent.user)
    resp = parent_client.get("/api/v1/notifications/", {"unread": "true"})
    assert resp.data["count"] == 1
    resp = parent_client.post(f"/api/v1/notifications/{n.id}/read/")
    assert resp.status_code == 200
    resp = parent_client.get("/api/v1/notifications/", {"unread": "true"})
    assert resp.data["count"] == 0


def test_cannot_read_foreign_notification(parent_client, doctor):
    n = make_notification(doctor.user)
    resp = parent_client.post(f"/api/v1/notifications/{n.id}/read/")
    assert resp.status_code == 404


def test_mark_all_read_only_affects_own_unread(parent, parent_client, doctor):
    make_notification(parent.user)
    make_notification(parent.user)
    other = make_notification(doctor.user)
    resp = parent_client.post("/api/v1/notifications/read-all/")
    assert resp.status_code == 200
    assert resp.data["marked_read"] == 2
    resp = parent_client.get("/api/v1/notifications/", {"unread": "true"})
    assert resp.data["count"] == 0
    other.refresh_from_db()
    assert other.read_at is None  # untouched


def test_device_token_upsert_and_delete(parent, parent_client):
    resp = parent_client.post(
        "/api/v1/notifications/device-tokens/",
        {"token": "fcm-token-abc", "platform": "android"}, format="json",
    )
    assert resp.status_code == 201
    # Same token re-registered → idempotent (still 1 row)
    parent_client.post(
        "/api/v1/notifications/device-tokens/",
        {"token": "fcm-token-abc", "platform": "android"}, format="json",
    )
    assert DeviceToken.objects.count() == 1

    resp = parent_client.delete(
        "/api/v1/notifications/device-tokens/", {"token": "fcm-token-abc"}, format="json"
    )
    assert resp.status_code == 204
    assert DeviceToken.objects.count() == 0


def test_category_filter(parent, parent_client):
    make_notification(parent.user, category="alert")
    make_notification(parent.user, category="medical")
    resp = parent_client.get("/api/v1/notifications/", {"category": "medical"})
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["category"] == "medical"


def test_delete_own_notification(parent, parent_client):
    n = make_notification(parent.user)
    resp = parent_client.delete(f"/api/v1/notifications/{n.id}/")
    assert resp.status_code == 204
    assert not Notification.objects.filter(pk=n.id).exists()


def test_cannot_delete_someone_elses_notification(parent_client, doctor):
    n = make_notification(doctor.user)
    resp = parent_client.delete(f"/api/v1/notifications/{n.id}/")
    assert resp.status_code == 404
    assert Notification.objects.filter(pk=n.id).exists()


def test_welcome_notification_sent_on_registration():
    from rest_framework.test import APIClient

    client = APIClient()
    # Parent self-registration is closed (REFONTE §3.4); doctors still self-register.
    resp = client.post(
        "/api/v1/auth/register",
        {
            "email": "new.doctor@example.com", "password": "s3cur3pass!",
            "first_name": "New", "last_name": "Doctor", "role": "doctor",
            "license_number": "LIC-424242",
        },
        format="json",
    )
    assert resp.status_code == 201
    user_id = resp.data["user"]["id"]
    notif = Notification.objects.filter(user_id=user_id, category="system").first()
    assert notif is not None
    assert "Welcome" in notif.title


def test_belt_pair_and_unpair_notify_parent(parent, parent_client, baby):
    from tests.factories import beltFactory

    belt = beltFactory(baby=None)
    parent_client.post(f"/api/v1/belts/{belt.id}/pair/", {"baby_id": baby.id}, format="json")
    assert Notification.objects.filter(
        user=parent.user, category="belt", title="belt paired"
    ).exists()

    parent_client.post(f"/api/v1/belts/{belt.id}/unpair/")
    assert Notification.objects.filter(
        user=parent.user, category="belt", title="belt disconnected"
    ).exists()


def test_preferences_default_all_enabled(parent_client):
    resp = parent_client.get("/api/v1/notifications/preferences/")
    assert resp.status_code == 200
    assert resp.data == {"belt": True, "medical": True, "system": True}


def test_muting_a_category_suppresses_notify(parent, parent_client):
    from notifications.utils import notify

    parent_client.patch(
        "/api/v1/notifications/preferences/", {"belt": False}, format="json"
    )
    result = notify(parent.user, "belt paired", "…", category="belt")
    assert result is None
    assert not Notification.objects.filter(user=parent.user, category="belt").exists()

    # Unaffected category still delivers.
    result2 = notify(parent.user, "Welcome", "…", category="system")
    assert result2 is not None


def test_alert_category_cannot_be_muted(parent, parent_client):
    from notifications.utils import notify

    resp = parent_client.patch(
        "/api/v1/notifications/preferences/", {"alert": False}, format="json"
    )
    # 'alert' isn't a mutable category — silently ignored, not an error.
    assert resp.status_code == 200
    result = notify(parent.user, "High temperature", "…", category="alert")
    assert result is not None


def test_notification_ordering(parent, parent_client):
    make_notification(parent.user, title="First")
    make_notification(parent.user, title="Second")
    resp = parent_client.get("/api/v1/notifications/", {"ordering": "created_at"})
    assert resp.status_code == 200
    assert resp.data["results"][0]["title"] == "First"
