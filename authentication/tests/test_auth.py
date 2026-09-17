"""Auth flow tests: register, login, refresh rotation, logout revocation."""
import pytest

from authentication.models import Session
from users.models import Doctor, Parent, User

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"

PARENT_PAYLOAD = {
    "email": "maman@example.com",
    "password": "S3curePassw0rd!",
    "first_name": "Marie",
    "last_name": "Dupont",
    "role": "parent",
    "address": "1 Rue A",
    "emergency_contact": "+33612345678",
}


def test_register_parent_creates_profile_and_session(api):
    resp = api.post(REGISTER_URL, PARENT_PAYLOAD, format="json")
    assert resp.status_code == 201
    assert "access" in resp.data and "refresh" in resp.data
    assert resp.data["user"]["role"] == "parent"
    user = User.objects.get(email="maman@example.com")
    assert Parent.objects.filter(user=user).exists()
    assert Session.objects.filter(user=user, revoked_at__isnull=True).count() == 1
    # Password is hashed, never stored in clear
    assert user.password != PARENT_PAYLOAD["password"]
    assert user.check_password(PARENT_PAYLOAD["password"])


def test_register_doctor_requires_license(api):
    payload = {**PARENT_PAYLOAD, "email": "doc@example.com", "role": "doctor"}
    resp = api.post(REGISTER_URL, payload, format="json")
    assert resp.status_code == 400
    assert "license_number" in resp.data

    payload["license_number"] = "LIC-123456"
    resp = api.post(REGISTER_URL, payload, format="json")
    assert resp.status_code == 201
    assert Doctor.objects.filter(user__email="doc@example.com").exists()


def test_register_rejects_duplicate_email_and_weak_password(api):
    api.post(REGISTER_URL, PARENT_PAYLOAD, format="json")
    resp = api.post(REGISTER_URL, PARENT_PAYLOAD, format="json")
    assert resp.status_code == 400  # duplicate

    weak = {**PARENT_PAYLOAD, "email": "x@example.com", "password": "short"}
    resp = api.post(REGISTER_URL, weak, format="json")
    assert resp.status_code == 400  # min_length 10


def test_login_ok_and_bad_credentials(api):
    api.post(REGISTER_URL, PARENT_PAYLOAD, format="json")
    resp = api.post(LOGIN_URL, {"email": "maman@example.com", "password": "S3curePassw0rd!"}, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data

    resp = api.post(LOGIN_URL, {"email": "maman@example.com", "password": "wrong"}, format="json")
    assert resp.status_code == 401


def test_refresh_rotates_and_revokes_old_token(api):
    reg = api.post(REGISTER_URL, PARENT_PAYLOAD, format="json")
    old_refresh = reg.data["refresh"]

    resp = api.post(REFRESH_URL, {"refresh": old_refresh}, format="json")
    assert resp.status_code == 200
    new_refresh = resp.data["refresh"]
    assert new_refresh != old_refresh

    # Old refresh token is now revoked (rotation)
    resp = api.post(REFRESH_URL, {"refresh": old_refresh}, format="json")
    assert resp.status_code == 401


def test_logout_revokes_session(api):
    reg = api.post(REGISTER_URL, PARENT_PAYLOAD, format="json")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {reg.data['access']}")
    resp = api.post(LOGOUT_URL, {"refresh": reg.data["refresh"]}, format="json")
    assert resp.status_code == 200

    resp = api.post(REFRESH_URL, {"refresh": reg.data["refresh"]}, format="json")
    assert resp.status_code == 401


def test_protected_endpoint_requires_auth(api):
    resp = api.get("/api/v1/babies/")
    assert resp.status_code == 401
