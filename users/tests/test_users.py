"""Profile endpoints + admin-only user list tests."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_me_endpoint(parent_client, parent):
    resp = parent_client.get("/api/v1/me/")
    assert resp.status_code == 200
    assert resp.data["email"] == parent.user.email
    assert resp.data["role"] == "parent"


def test_doctor_updates_own_profile(doctor, doctor_client):
    resp = doctor_client.put(
        f"/api/v1/doctors/{doctor.id}/",
        {"user": {"first_name": "New", "last_name": "Name", "phone": "+33611111111"},
         "license_number": doctor.license_number, "specialty": "Pediatrics"},
        format="json",
    )
    assert resp.status_code == 200
    doctor.refresh_from_db()
    assert doctor.specialty == "Pediatrics"
    assert doctor.user.first_name == "New"


def test_parent_cannot_edit_foreign_doctor(parent_client, doctor):
    resp = parent_client.put(
        f"/api/v1/doctors/{doctor.id}/",
        {"user": {"first_name": "Hack"}, "license_number": "X", "specialty": "X"},
        format="json",
    )
    assert resp.status_code == 403


def test_user_list_admin_only(parent_client, admin_client):
    resp = parent_client.get("/api/v1/users/")
    assert resp.status_code == 403
    resp = admin_client.get("/api/v1/users/")
    assert resp.status_code == 200


def test_parent_list_admin_only(parent_client, admin_client, parent):
    resp = parent_client.get("/api/v1/parents/")
    assert resp.status_code == 403
    resp = admin_client.get("/api/v1/parents/")
    assert resp.status_code == 200
    assert any(p["id"] == parent.id for p in resp.data["results"])


def test_me_patch_updates_own_basic_fields(parent_client, parent):
    resp = parent_client.patch(
        "/api/v1/me/", {"first_name": "Updated"}, format="json"
    )
    assert resp.status_code == 200
    parent.user.refresh_from_db()
    assert parent.user.first_name == "Updated"


def test_me_patch_cannot_change_role(parent_client, parent):
    resp = parent_client.patch("/api/v1/me/", {"role": "admin"}, format="json")
    assert resp.status_code == 200
    parent.user.refresh_from_db()
    assert parent.user.role == "parent"  # read-only field, silently ignored


def test_audit_log_written_on_sensitive_access(parent_client, baby):
    from common.models import AuditLog

    parent_client.get("/api/v1/babies/")
    assert AuditLog.objects.filter(path="/api/v1/babies/").exists()


def test_deactivate_requires_correct_password(parent_client):
    resp = parent_client.post("/api/v1/me/deactivate/", {"password": "WrongPassword!"}, format="json")
    assert resp.status_code == 400


def test_deactivate_revokes_sessions_and_blocks_login(parent, parent_client):
    from authentication.models import Session

    Session.objects.create(
        user=parent.user, refresh_jti="abc123", expires_at=timezone.now() + timedelta(days=1)
    )
    resp = parent_client.post(
        "/api/v1/me/deactivate/", {"password": "S3curePassw0rd!"}, format="json"
    )
    assert resp.status_code == 200
    parent.user.refresh_from_db()
    assert parent.user.is_active is False
    assert not Session.objects.filter(user=parent.user, revoked_at__isnull=True).exists()

    login = APIClient().post(
        "/api/v1/auth/login",
        {"email": parent.user.email, "password": "S3curePassw0rd!"},
        format="json",
    )
    assert login.status_code == 401
