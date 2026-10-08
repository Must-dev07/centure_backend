"""Enrollment refonte — baby creation by doctors/admins (REFONTE §2.1, §3.1, §7)
and the record-level permissions (§3.6, deletion)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from babies.models import ENROLLMENT_HISTORY_TITLE, Baby, MedicalHistoryEntry
from invitations.models import Invitation
from tests.factories import BabyFactory, DoctorFactory, InvitationFactory, ParentFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/babies/"


def enroll(client, **overrides):
    payload = {
        "name": "Léa", "birth_date": "2026-07-01", "weight_grams": 3100, "gender": "female",
        "enrollment_reason": "prematurity", "enrollment_notes": "Née à 32 SA",
        "gestational_age_weeks": 32, "parent_email": "new.parent@example.com",
    }
    payload.update(overrides)
    return client.post(URL, payload, format="json")


# --- §7 required cases -------------------------------------------------------

def test_parent_cannot_create_baby(parent_client):
    resp = enroll(parent_client)
    assert resp.status_code == 403
    assert not Baby.objects.exists()
    assert not Invitation.objects.exists()


def test_doctor_with_existing_parent_email_links_directly(doctor_client):
    existing = ParentFactory(user__email="maman@example.com")
    resp = enroll(doctor_client, parent_email="Maman@Example.com")
    assert resp.status_code == 201
    assert resp.data["parent_status"] == "linked"
    assert resp.data["invitation_link"] is None
    baby = Baby.objects.get(pk=resp.data["id"])
    assert baby.parent_id == existing.id
    assert not Invitation.objects.exists()


def test_doctor_with_unknown_email_creates_pending_invitation(doctor, doctor_client):
    resp = enroll(doctor_client, parent_email="inconnu@example.com")
    assert resp.status_code == 201
    assert resp.data["parent_status"] == "invitation_pending"
    baby = Baby.objects.get(pk=resp.data["id"])
    assert baby.parent is None
    invitation = Invitation.objects.get()
    assert invitation.status == Invitation.Status.PENDING
    assert invitation.email == "inconnu@example.com"
    assert invitation.created_by == doctor.user
    assert list(invitation.babies.all()) == [baby]
    assert resp.data["invitation_link"] == f"app://invite/{invitation.token}"


def test_same_unregistered_email_reuses_pending_invitation(doctor_client):
    first = enroll(doctor_client, name="Premier", parent_email="twins@example.com")
    second = enroll(doctor_client, name="Second", parent_email="TWINS@example.com")
    assert first.status_code == second.status_code == 201
    assert Invitation.objects.count() == 1
    invitation = Invitation.objects.get()
    assert invitation.babies.count() == 2
    assert first.data["invitation_link"] == second.data["invitation_link"]


# --- Enrollment details (owner decisions) --------------------------------------

def test_invitation_valid_seven_days_and_token_format(doctor_client):
    before = timezone.now()
    enroll(doctor_client, parent_email="seven@example.com")
    invitation = Invitation.objects.get()
    expected = before + timedelta(days=7)
    assert expected - timedelta(minutes=1) <= invitation.expires_at <= expected + timedelta(minutes=1)
    assert 0 < len(invitation.token) <= 64


def test_expired_pending_invitation_is_not_reused(doctor_client):
    stale = InvitationFactory(
        email="late@example.com", expires_at=timezone.now() - timedelta(hours=1)
    )
    resp = enroll(doctor_client, parent_email="late@example.com")
    assert resp.status_code == 201
    stale.refresh_from_db()
    assert stale.status == Invitation.Status.EXPIRED
    fresh = Invitation.objects.exclude(pk=stale.pk).get()
    assert fresh.status == Invitation.Status.PENDING
    assert resp.data["invitation_link"] == f"app://invite/{fresh.token}"
    assert fresh.token != stale.token


def test_other_reason_requires_notes(doctor_client):
    resp = enroll(doctor_client, enrollment_reason="other", enrollment_notes="  ")
    assert resp.status_code == 400
    assert "enrollment_notes" in resp.data
    assert not Baby.objects.exists()

    resp = enroll(doctor_client, enrollment_reason="other", enrollment_notes="Hypotonie observée")
    assert resp.status_code == 201


def test_invalid_enrollment_reason_rejected(doctor_client):
    resp = enroll(doctor_client, enrollment_reason="unknown")
    assert resp.status_code == 400


def test_doctor_enrollment_history_entry_records_doctor(doctor, doctor_client):
    resp = enroll(doctor_client, enrollment_notes="Détresse respiratoire")
    baby = Baby.objects.get(pk=resp.data["id"])
    assert baby.enrolled_by == doctor.user
    entry = MedicalHistoryEntry.objects.get(baby=baby)
    assert entry.title == ENROLLMENT_HISTORY_TITLE == "Enrôlement"
    assert entry.details == "Détresse respiratoire"
    assert entry.recorded_by == doctor
    assert resp.data["enrolled_by"] == doctor.user.id


def test_admin_enrollment_history_entry_has_no_doctor(admin_user, admin_client):
    resp = enroll(admin_client)
    assert resp.status_code == 201
    baby = Baby.objects.get(pk=resp.data["id"])
    assert baby.enrolled_by == admin_user
    entry = MedicalHistoryEntry.objects.get(baby=baby)
    assert entry.title == "Enrôlement"
    assert entry.recorded_by is None  # never a fabricated doctor


def test_enrollment_entry_only_on_creation(doctor, doctor_client):
    resp = enroll(doctor_client)
    baby = Baby.objects.get(pk=resp.data["id"])
    baby.enrollment_notes = "Mise à jour"
    baby.save()
    assert MedicalHistoryEntry.objects.filter(baby=baby).count() == 1


def test_admin_enrollment_with_assigned_doctor(admin_client):
    other = DoctorFactory()
    resp = enroll(admin_client, assigned_doctor=other.id)
    assert resp.status_code == 201
    assert resp.data["assigned_doctor"] == other.id


def test_doctor_cannot_assign_doctor_at_enrollment(doctor_client):
    other = DoctorFactory()
    resp = enroll(doctor_client, assigned_doctor=other.id)
    assert resp.status_code == 403
    assert not Baby.objects.exists()


# --- §3.6 edit and deletion permissions ---------------------------------------

def test_assigned_doctor_can_patch_enrollment_fields(doctor, doctor_client):
    baby = BabyFactory(assigned_doctor=doctor)
    resp = doctor_client.patch(
        f"{URL}{baby.id}/", {"enrollment_notes": "Précision", "gestational_age_weeks": 34}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["enrollment_notes"] == "Précision"
    assert resp.data["gestational_age_weeks"] == 34


def test_assigned_doctor_can_patch_weight_and_height(doctor, doctor_client):
    baby = BabyFactory(assigned_doctor=doctor)
    resp = doctor_client.patch(
        f"{URL}{baby.id}/", {"weight_grams": 4000, "height_cm": "52.5"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["weight_grams"] == 4000
    assert resp.data["height_cm"] == "52.5"


def test_height_is_bounded(doctor, doctor_client):
    baby = BabyFactory(assigned_doctor=doctor)
    resp = doctor_client.patch(f"{URL}{baby.id}/", {"height_cm": "5"}, format="json")
    assert resp.status_code == 400
    assert "height_cm" in resp.data


def test_assigned_doctor_still_cannot_patch_identity_fields(doctor, doctor_client):
    baby = BabyFactory(assigned_doctor=doctor)
    for field, value in (("name", "Renamed"), ("birth_date", "2026-07-02"), ("gender", "female")):
        resp = doctor_client.patch(
            f"{URL}{baby.id}/", {field: value, "weight_grams": 4000}, format="json"
        )
        assert resp.status_code == 403, field
    baby.refresh_from_db()
    assert baby.weight_grams != 4000


def test_admin_can_patch_baby(admin_client):
    baby = BabyFactory()
    resp = admin_client.patch(f"{URL}{baby.id}/", {"name": "Renamed"}, format="json")
    assert resp.status_code == 200
    assert resp.data["name"] == "Renamed"


def test_other_doctor_cannot_patch_baby(doctor_client):
    baby = BabyFactory()  # assigned to another doctor
    resp = doctor_client.patch(f"{URL}{baby.id}/", {"enrollment_notes": "x"}, format="json")
    assert resp.status_code == 404  # outside the doctor's queryset


def test_patch_other_without_notes_rejected(admin_client):
    baby = BabyFactory()
    resp = admin_client.patch(f"{URL}{baby.id}/", {"enrollment_reason": "other"}, format="json")
    assert resp.status_code == 400


def test_parent_put_is_forbidden(parent_client, parent):
    baby = BabyFactory(parent=parent)
    resp = parent_client.put(
        f"{URL}{baby.id}/",
        {"name": "X", "birth_date": "2026-07-01", "weight_grams": 3000, "gender": "male",
         "enrollment_reason": "prematurity"},
        format="json",
    )
    assert resp.status_code == 403


def test_admin_can_delete_baby(admin_client):
    baby = BabyFactory()
    resp = admin_client.delete(f"{URL}{baby.id}/")
    assert resp.status_code == 204
    assert not Baby.objects.filter(pk=baby.pk).exists()


# --- §4 read access unchanged ---------------------------------------------------

def test_read_access_unchanged(parent, parent_client, doctor, doctor_client, admin_client):
    baby = BabyFactory(parent=parent, assigned_doctor=doctor)
    assert parent_client.get(f"{URL}{baby.id}/").status_code == 200
    assert doctor_client.get(f"{URL}{baby.id}/").status_code == 200
    assert admin_client.get(f"{URL}{baby.id}/").status_code == 200
    assert parent_client.get(URL).data["count"] == 1
    assert doctor_client.get(URL).data["count"] == 1


def test_parent_cannot_see_babies_without_parent(parent_client, doctor):
    orphan = BabyFactory(parent=None, assigned_doctor=doctor)
    assert parent_client.get(URL).data["count"] == 0
    assert parent_client.get(f"{URL}{orphan.id}/").status_code == 404
