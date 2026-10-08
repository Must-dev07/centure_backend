"""REFONTE §3.2: GET /parents/ is a directory for doctors and admins with
?search= on email/name. The existing endpoint is extended (same path, response
shape, pagination); it is not duplicated."""
import pytest

from tests.factories import ParentFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/parents/"


def test_doctor_and_admin_allowed_parent_refused(parent_client, doctor_client, admin_client):
    assert parent_client.get(URL).status_code == 403
    assert doctor_client.get(URL).status_code == 200
    assert admin_client.get(URL).status_code == 200


def test_search_by_email_and_name(doctor_client):
    marie = ParentFactory(user__email="marie.dupont@example.com", user__first_name="Marie", user__last_name="Dupont")
    ParentFactory(user__email="paul@example.com", user__first_name="Paul", user__last_name="Martin")

    by_email = doctor_client.get(URL, {"search": "MARIE.DUPONT@"}).data
    assert [p["id"] for p in by_email["results"]] == [marie.id]

    by_last_name = doctor_client.get(URL, {"search": "dupont"}).data
    assert [p["id"] for p in by_last_name["results"]] == [marie.id]

    by_first_name = doctor_client.get(URL, {"search": "Marie"}).data
    assert [p["id"] for p in by_first_name["results"]] == [marie.id]

    assert doctor_client.get(URL, {"search": "nobody"}).data["count"] == 0


def test_response_shape_and_pagination_unchanged(admin_client, parent):
    resp = admin_client.get(URL)
    assert set(resp.data) >= {"count", "next", "previous", "results"}
    item = next(p for p in resp.data["results"] if p["id"] == parent.id)
    assert item["user"]["email"] == parent.user.email
    assert {"id", "user", "address", "emergency_contact"} <= set(item)
