"""REFONTE §3.5: pair/unpair allowed for the owning parent, the doctor assigned
to the baby, or an admin (request/response schema unchanged)."""
import pytest

from belts.models import belt
from tests.factories import BabyFactory, beltFactory, DoctorFactory

pytestmark = pytest.mark.django_db


def pair(client, belt, baby):
    return client.post(f"/api/v1/belts/{belt.id}/pair/", {"baby_id": baby.id}, format="json")


def test_assigned_doctor_can_pair(doctor, doctor_client):
    # §7: "Pairing par le docteur assigné → 200". The endpoint's existing
    # success status is 201 Created and its schema must not change (§3.5).
    baby = BabyFactory(assigned_doctor=doctor)
    belt = beltFactory()
    resp = pair(doctor_client, belt, baby)
    assert resp.status_code == 201
    belt.refresh_from_db()
    assert belt.baby_id == baby.id
    assert belt.status == belt.Status.ACTIVE


def test_assigned_doctor_can_unpair(doctor, doctor_client):
    baby = BabyFactory(assigned_doctor=doctor)
    belt = beltFactory()
    belt.pair_with(baby)
    resp = doctor_client.post(f"/api/v1/belts/{belt.id}/unpair/")
    assert resp.status_code == 200
    belt.refresh_from_db()
    assert belt.baby is None


def test_non_assigned_doctor_cannot_pair(doctor_client):
    baby = BabyFactory(assigned_doctor=DoctorFactory())
    belt = beltFactory()
    resp = pair(doctor_client, belt, baby)
    assert resp.status_code == 403
    belt.refresh_from_db()
    assert belt.baby is None


def test_non_assigned_doctor_cannot_unpair(doctor_client):
    baby = BabyFactory(assigned_doctor=DoctorFactory())
    belt = beltFactory()
    belt.pair_with(baby)
    resp = doctor_client.post(f"/api/v1/belts/{belt.id}/unpair/")
    assert resp.status_code == 404  # belt outside the doctor's scope
    belt.refresh_from_db()
    assert belt.baby_id == baby.id


def test_admin_can_pair_and_unpair(admin_client):
    baby = BabyFactory()
    belt = beltFactory()
    assert pair(admin_client, belt, baby).status_code == 201
    assert admin_client.post(f"/api/v1/belts/{belt.id}/unpair/").status_code == 200


def test_owning_parent_can_still_pair(parent, parent_client):
    baby = BabyFactory(parent=parent)
    belt = beltFactory()
    assert pair(parent_client, belt, baby).status_code == 201


def test_doctor_belt_listing_unchanged(doctor, doctor_client):
    # Unassigned belts are pairable by a doctor, but the listing scope is unchanged.
    beltFactory()
    resp = doctor_client.get("/api/v1/belts/")
    assert resp.status_code == 200
    assert resp.data["count"] == 0


def test_assigned_doctor_finds_unassigned_belt_by_serial(doctor, doctor_client):
    # The mobile pairing flow looks an already-registered belt up by serial.
    belt = beltFactory()
    resp = doctor_client.get("/api/v1/belts/", {"serial_number": belt.serial_number})
    assert resp.status_code == 200
    assert [b["id"] for b in resp.data["results"]] == [belt.id]

    # The plain listing scope is unchanged: unassigned belts stay out of it.
    resp = doctor_client.get("/api/v1/belts/")
    assert belt.id not in [b["id"] for b in resp.data["results"]]


def test_serial_lookup_hides_other_doctors_belts(doctor_client):
    other_baby = BabyFactory()  # assigned to another doctor
    belt = beltFactory()
    belt.pair_with(other_baby)
    resp = doctor_client.get("/api/v1/belts/", {"serial_number": belt.serial_number})
    assert resp.status_code == 200
    assert resp.data["results"] == []
