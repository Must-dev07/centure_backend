"""Doctor assignment request workflow (Section 3): parent requests a doctor,
the doctor accepts/declines; only acceptance changes Baby.assigned_doctor.
Admins bypass this and assign directly; a doctor may self-remove.
"""
import pytest
from rest_framework.test import APIClient

from tests.factories import BabyFactory, DoctorFactory, ParentFactory

pytestmark = pytest.mark.django_db


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def unassigned_baby(parent):
    return BabyFactory(parent=parent, assigned_doctor=None)


def test_parent_requests_doctor_creates_pending_request(parent_client, unassigned_baby, doctor):
    resp = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/",
        {"doctor": doctor.id, "note": "Our paediatrician recommended you."},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["status"] == "pending"
    unassigned_baby.refresh_from_db()
    assert unassigned_baby.assigned_doctor_id is None  # not assigned until accepted


def test_cannot_request_doctor_for_someone_elses_baby(parent_client, doctor):
    other_baby = BabyFactory(assigned_doctor=None)  # different parent
    resp = parent_client.post(
        f"/api/v1/babies/{other_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    assert resp.status_code in (403, 404)


def test_duplicate_pending_request_rejected(parent_client, unassigned_baby, doctor):
    other_doctor = DoctorFactory()
    parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    resp = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/",
        {"doctor": other_doctor.id},
        format="json",
    )
    assert resp.status_code == 400


def test_doctor_accepts_request_assigns_baby_and_notifies_parent(
    parent_client, unassigned_baby, doctor
):
    create = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    req_id = create.data["id"]

    doctor_client = _client_for(doctor.user)
    resp = doctor_client.post(f"/api/v1/babies/doctor-requests/{req_id}/accept/")
    assert resp.status_code == 200
    assert resp.data["status"] == "accepted"

    unassigned_baby.refresh_from_db()
    assert unassigned_baby.assigned_doctor_id == doctor.id

    notif = parent_client.get("/api/v1/notifications/")
    assert any("accepted" in n["title"].lower() for n in notif.data["results"])


def test_accepting_one_request_auto_declines_other_pending_requests(parent_client, unassigned_baby):
    doc_a, doc_b = DoctorFactory(), DoctorFactory()
    r1 = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doc_a.id}, format="json"
    )
    # cancel first so a second pending request is allowed, then create both "pending" via admin bypass check:
    # simpler: decline path isn't needed here — just verify accept closes competing pendings by
    # creating a second request directly against the model after cancelling the dedup guard.
    from babies.models import DoctorAssignmentRequest

    DoctorAssignmentRequest.objects.filter(pk=r1.data["id"]).update(status="pending")
    r2 = DoctorAssignmentRequest.objects.create(baby=unassigned_baby, doctor=doc_b, status="pending")

    doctor_client = _client_for(doc_a.user)
    resp = doctor_client.post(f"/api/v1/babies/doctor-requests/{r1.data['id']}/accept/")
    assert resp.status_code == 200

    r2.refresh_from_db()
    assert r2.status == "declined"


def test_only_requested_doctor_can_accept(parent_client, unassigned_baby, doctor):
    create = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    other_doctor_client = _client_for(DoctorFactory().user)
    resp = other_doctor_client.post(f"/api/v1/babies/doctor-requests/{create.data['id']}/accept/")
    assert resp.status_code == 403


def test_doctor_declines_request(parent_client, unassigned_baby, doctor):
    create = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    doctor_client = _client_for(doctor.user)
    resp = doctor_client.post(f"/api/v1/babies/doctor-requests/{create.data['id']}/decline/")
    assert resp.status_code == 200
    assert resp.data["status"] == "declined"
    unassigned_baby.refresh_from_db()
    assert unassigned_baby.assigned_doctor_id is None


def test_requester_can_cancel_pending_request(parent_client, unassigned_baby, doctor):
    create = parent_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    resp = parent_client.post(f"/api/v1/babies/doctor-requests/{create.data['id']}/cancel/")
    assert resp.status_code == 200
    assert resp.data["status"] == "cancelled"


def test_stranger_cannot_cancel_request(unassigned_baby, doctor):
    create_client = _client_for(unassigned_baby.parent.user)
    create = create_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    stranger_client = _client_for(ParentFactory().user)
    resp = stranger_client.post(f"/api/v1/babies/doctor-requests/{create.data['id']}/cancel/")
    assert resp.status_code == 403


def test_doctor_sees_own_pending_inbox(doctor, doctor_client, unassigned_baby):
    unassigned_baby_client = _client_for(unassigned_baby.parent.user)
    unassigned_baby_client.post(
        f"/api/v1/babies/{unassigned_baby.id}/doctor-requests/", {"doctor": doctor.id}, format="json"
    )
    resp = doctor_client.get("/api/v1/babies/doctor-requests/", {"status": "pending"})
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["doctor"] == doctor.id


def test_parent_cannot_directly_patch_assigned_doctor(parent_client, unassigned_baby, doctor):
    resp = parent_client.patch(
        f"/api/v1/babies/{unassigned_baby.id}/", {"assigned_doctor": doctor.id}, format="json"
    )
    assert resp.status_code == 403
    unassigned_baby.refresh_from_db()
    assert unassigned_baby.assigned_doctor_id is None


def test_admin_can_directly_assign_and_remove_doctor(admin_client, unassigned_baby, doctor):
    resp = admin_client.patch(
        f"/api/v1/babies/{unassigned_baby.id}/", {"assigned_doctor": doctor.id}, format="json"
    )
    assert resp.status_code == 200
    unassigned_baby.refresh_from_db()
    assert unassigned_baby.assigned_doctor_id == doctor.id

    resp = admin_client.patch(
        f"/api/v1/babies/{unassigned_baby.id}/", {"assigned_doctor": None}, format="json"
    )
    assert resp.status_code == 200
    unassigned_baby.refresh_from_db()
    assert unassigned_baby.assigned_doctor_id is None


def test_doctor_can_remove_self_but_not_reassign_to_another_doctor(doctor_client, baby, doctor):
    # `baby` fixture is pre-assigned to `doctor`.
    other_doctor = DoctorFactory()
    resp = doctor_client.patch(
        f"/api/v1/babies/{baby.id}/", {"assigned_doctor": other_doctor.id}, format="json"
    )
    assert resp.status_code == 403

    resp = doctor_client.patch(
        f"/api/v1/babies/{baby.id}/", {"assigned_doctor": None}, format="json"
    )
    assert resp.status_code == 200
    baby.refresh_from_db()
    assert baby.assigned_doctor_id is None
