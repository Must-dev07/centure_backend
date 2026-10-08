"""Invitation endpoints (REFONTE §3.3 + owner decisions): listing without
tokens, public acceptance (404/410/400/401/409), resend, expiry watchdog."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import Session
from invitations.models import Invitation
from invitations.tasks import expire_invitations
from tests.factories import (
    BabyFactory,
    DoctorFactory,
    InvitationFactory,
    ParentFactory,
    UserFactory,
)
from users.models import Parent, User

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/invitations/"
PASSWORD = "N0uveauMotDePasse!"


def accept_url(token):
    return f"/api/v1/invitations/{token}/accept/"


def resend_url(pk):
    return f"/api/v1/invitations/{pk}/resend/"


@pytest.fixture
def invitation(doctor):
    """A pending invitation created by `doctor` for two parent-less babies."""
    inv = InvitationFactory(email="invitee@example.com", created_by=doctor.user)
    inv.babies.add(
        BabyFactory(parent=None, assigned_doctor=doctor),
        BabyFactory(parent=None, assigned_doctor=doctor),
    )
    return inv


# --- Listing ----------------------------------------------------------------------

def test_list_never_exposes_token_or_link(invitation, doctor_client):
    resp = doctor_client.get(LIST_URL, {"status": "pending"})
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    item = resp.data["results"][0]
    assert "token" not in item
    assert "invitation_link" not in item
    assert invitation.token not in str(resp.data)
    assert {b["id"] for b in item["babies"]} == set(invitation.babies.values_list("id", flat=True))
    for field in ("id", "email", "status", "created_by", "created_at", "expires_at", "accepted_at"):
        assert field in item


def test_list_permissions(invitation, parent_client, admin_client):
    assert parent_client.get(LIST_URL).status_code == 403
    assert APIClient().get(LIST_URL).status_code == 401
    assert admin_client.get(LIST_URL).data["count"] == 1


def test_doctor_list_scope(doctor, doctor_client, invitation):
    # Invitation for a baby assigned to this doctor, created by someone else: visible.
    assigned = InvitationFactory()
    assigned.babies.add(BabyFactory(parent=None, assigned_doctor=doctor))
    # Unrelated invitation: not visible.
    unrelated = InvitationFactory()
    unrelated.babies.add(BabyFactory(parent=None, assigned_doctor=DoctorFactory()))

    ids = {i["id"] for i in doctor_client.get(LIST_URL).data["results"]}
    assert ids == {invitation.id, assigned.id}


def test_list_status_filter(invitation, admin_client):
    InvitationFactory(status=Invitation.Status.EXPIRED)
    pending = admin_client.get(LIST_URL, {"status": "pending"}).data
    assert [i["id"] for i in pending["results"]] == [invitation.id]
    expired = admin_client.get(LIST_URL, {"status": "expired"}).data
    assert expired["count"] == 1


# --- Acceptance ---------------------------------------------------------------------

def test_accept_valid_invitation_creates_account(invitation):
    resp = APIClient().post(
        accept_url(invitation.token),
        {"password": PASSWORD, "first_name": "Marie", "last_name": "Dupont", "phone": "+33600000001"},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    assert resp.data["user"]["role"] == "parent"
    user = User.objects.get(email="invitee@example.com")
    assert user.role == "parent" and user.first_name == "Marie" and user.phone == "+33600000001"
    assert user.check_password(PASSWORD)
    parent = Parent.objects.get(user=user)
    assert set(parent.babies.all()) == set(invitation.babies.all())
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.ACCEPTED
    assert invitation.accepted_at is not None
    assert Session.objects.filter(user=user, revoked_at__isnull=True).count() == 1
    # The returned access token works on an authenticated endpoint.
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    assert client.get("/api/v1/babies/").data["count"] == 2


def test_accept_unknown_token_404():
    resp = APIClient().post(accept_url("does-not-exist"), {"password": PASSWORD}, format="json")
    assert resp.status_code == 404


def test_accept_expired_invitation_410(invitation):
    invitation.status = Invitation.Status.EXPIRED
    invitation.save()
    resp = APIClient().post(accept_url(invitation.token), {"password": PASSWORD}, format="json")
    assert resp.status_code == 410
    assert not User.objects.filter(email="invitee@example.com").exists()


def test_accept_pending_past_expiry_410(invitation):
    invitation.expires_at = timezone.now() - timedelta(minutes=1)
    invitation.save()
    resp = APIClient().post(accept_url(invitation.token), {"password": PASSWORD}, format="json")
    assert resp.status_code == 410
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.PENDING  # nothing changed
    assert invitation.babies.filter(parent__isnull=False).count() == 0


def test_accept_already_accepted_410(invitation):
    client = APIClient()
    assert client.post(accept_url(invitation.token), {"password": PASSWORD}, format="json").status_code == 200
    resp = client.post(accept_url(invitation.token), {"password": PASSWORD}, format="json")
    assert resp.status_code == 410
    assert User.objects.filter(email="invitee@example.com").count() == 1


def test_accept_existing_parent_account_links_without_duplicate(invitation):
    existing = ParentFactory(user__email="invitee@example.com")  # password: S3curePassw0rd!
    users_before = User.objects.count()
    resp = APIClient().post(
        accept_url(invitation.token),
        {"password": "S3curePassw0rd!", "first_name": "Ignored"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["user"]["id"] == existing.user_id
    assert User.objects.count() == users_before
    assert Parent.objects.filter(user__email="invitee@example.com").count() == 1
    assert set(existing.babies.all()) == set(invitation.babies.all())
    existing.user.refresh_from_db()
    assert existing.user.first_name != "Ignored"  # profile not overwritten
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.ACCEPTED


def test_accept_existing_parent_wrong_password_401(invitation):
    ParentFactory(user__email="invitee@example.com")
    resp = APIClient().post(accept_url(invitation.token), {"password": "wrong-password"}, format="json")
    assert resp.status_code == 401
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.PENDING
    assert invitation.babies.filter(parent__isnull=False).count() == 0


def test_accept_email_of_doctor_account_409(invitation):
    DoctorFactory(user__email="invitee@example.com")
    resp = APIClient().post(accept_url(invitation.token), {"password": "S3curePassw0rd!"}, format="json")
    assert resp.status_code == 409
    assert not Parent.objects.filter(user__email="invitee@example.com").exists()
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.PENDING


def test_accept_email_of_admin_account_409(invitation):
    UserFactory(email="invitee@example.com", role="admin")
    resp = APIClient().post(accept_url(invitation.token), {"password": "S3curePassw0rd!"}, format="json")
    assert resp.status_code == 409


def test_accept_weak_password_400_creates_nothing(invitation):
    resp = APIClient().post(accept_url(invitation.token), {"password": "short"}, format="json")
    assert resp.status_code == 400
    assert "password" in resp.data
    assert not User.objects.filter(email="invitee@example.com").exists()
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.PENDING


def test_accept_missing_password_400(invitation):
    resp = APIClient().post(accept_url(invitation.token), {}, format="json")
    assert resp.status_code == 400


def test_accept_ignores_stale_bearer_token(invitation):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer not-a-valid-token")
    resp = client.post(accept_url(invitation.token), {"password": PASSWORD}, format="json")
    assert resp.status_code == 200


# --- Resend ------------------------------------------------------------------------

def test_resend_pending_issues_new_token_and_link(invitation, doctor_client):
    old_token = invitation.token
    before = timezone.now()
    resp = doctor_client.post(resend_url(invitation.id))
    assert resp.status_code == 200
    invitation.refresh_from_db()
    assert invitation.token != old_token
    assert invitation.status == Invitation.Status.PENDING
    expected = before + timedelta(days=7)
    assert expected - timedelta(minutes=1) <= invitation.expires_at <= expected + timedelta(minutes=1)
    assert resp.data["invitation_link"] == f"app://invite/{invitation.token}"
    assert "token" not in resp.data
    # The previous link no longer works; the new one does.
    client = APIClient()
    assert client.post(accept_url(old_token), {"password": PASSWORD}, format="json").status_code == 404
    assert client.post(accept_url(invitation.token), {"password": PASSWORD}, format="json").status_code == 200


def test_resend_expired_renews_invitation(invitation, admin_client):
    invitation.status = Invitation.Status.EXPIRED
    invitation.expires_at = timezone.now() - timedelta(days=1)
    invitation.save()
    resp = admin_client.post(resend_url(invitation.id))
    assert resp.status_code == 200
    invitation.refresh_from_db()
    assert invitation.status == Invitation.Status.PENDING
    assert invitation.expires_at > timezone.now() + timedelta(days=6)
    assert invitation.babies.count() == 2  # babies and email kept


def test_resend_accepted_409(invitation, admin_client):
    invitation.status = Invitation.Status.ACCEPTED
    invitation.save()
    token = invitation.token
    resp = admin_client.post(resend_url(invitation.id))
    assert resp.status_code == 409
    invitation.refresh_from_db()
    assert invitation.token == token
    assert invitation.status == Invitation.Status.ACCEPTED


def test_resend_permissions(invitation, parent_client):
    assert parent_client.post(resend_url(invitation.id)).status_code == 403
    assert APIClient().post(resend_url(invitation.id)).status_code == 401

    other_doctor = APIClient()
    other_doctor.force_authenticate(user=DoctorFactory().user)
    assert other_doctor.post(resend_url(invitation.id)).status_code == 404  # outside scope


def test_resend_unknown_invitation_404(admin_client):
    assert admin_client.post(resend_url(999999)).status_code == 404


# --- Watchdog ----------------------------------------------------------------------

def test_expire_invitations_watchdog():
    stale = InvitationFactory(expires_at=timezone.now() - timedelta(minutes=5))
    fresh = InvitationFactory()
    accepted = InvitationFactory(
        status=Invitation.Status.ACCEPTED, expires_at=timezone.now() - timedelta(days=1)
    )
    assert expire_invitations() == 1
    for inv in (stale, fresh, accepted):
        inv.refresh_from_db()
    assert stale.status == Invitation.Status.EXPIRED
    assert fresh.status == Invitation.Status.PENDING
    assert accepted.status == Invitation.Status.ACCEPTED
    assert Invitation.objects.count() == 3  # nothing deleted


def test_watchdog_registered_in_beat_schedule():
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["expire-invitations"]
    assert entry["task"] == "invitations.tasks.expire_invitations"
    assert "detect-no-data" in settings.CELERY_BEAT_SCHEDULE  # existing entry untouched
