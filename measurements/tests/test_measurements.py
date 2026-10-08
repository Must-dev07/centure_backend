"""Ingest (single + bulk), validation, query & granularity tests."""
from datetime import timedelta

import pytest
from django.utils import timezone

from alerts.models import Alert
from measurements.models import Measurement
from tests.factories import MeasurementFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/measurements/"


def _sample(belt, **kw):
    base = {
        "belt": belt.id,
        "heart_rate": 130,
        "temperature": 37.0,
        "respiratory_rate": 45,
        "battery": 80,
        "skin_contact": True,
        "recorded_at": timezone.now().isoformat(),
    }
    base.update(kw)
    return base


def test_single_ingest_updates_belt(parent_client, belt):
    resp = parent_client.post(URL, _sample(belt), format="json")
    assert resp.status_code == 201
    assert resp.data["created"] == 1
    belt.refresh_from_db()
    assert belt.last_seen_at is not None
    assert belt.battery_level == 80


def test_bulk_ingest(parent_client, belt):
    payload = [_sample(belt) for _ in range(10)]
    resp = parent_client.post(URL, payload, format="json")
    assert resp.status_code == 201
    assert resp.data["created"] == 10
    assert Measurement.objects.count() == 10


def test_ingest_activity_optional_and_validated(parent_client, belt):
    resp = parent_client.post(URL, _sample(belt), format="json")
    assert resp.status_code == 201
    assert Measurement.objects.get().activity == "unknown"  # older apps omit it

    resp = parent_client.post(URL, _sample(belt, activity="effort"), format="json")
    assert resp.status_code == 201
    assert Measurement.objects.filter(activity="effort").count() == 1

    resp = parent_client.post(URL, _sample(belt, activity="running"), format="json")
    assert resp.status_code == 400


def test_ingest_rejects_impossible_values(parent_client, belt):
    resp = parent_client.post(URL, _sample(belt, heart_rate=-5), format="json")
    assert resp.status_code == 400
    resp = parent_client.post(URL, _sample(belt, heart_rate=900), format="json")
    assert resp.status_code == 400
    resp = parent_client.post(URL, _sample(belt, respiratory_rate=-1), format="json")
    assert resp.status_code == 400
    resp = parent_client.post(URL, _sample(belt, respiratory_rate=200), format="json")
    assert resp.status_code == 400


def test_ingest_rejects_unpaired_belt(parent_client, belt):
    belt.unpair()
    resp = parent_client.post(URL, _sample(belt), format="json")
    assert resp.status_code == 400
    assert resp.data["errors"][0]["detail"] == "belt not paired."


def test_ingest_forbidden_on_foreign_belt(belt):
    # A doctor who is NOT the baby's assigned doctor → belt invisible
    from rest_framework.test import APIClient

    from tests.factories import DoctorFactory

    other_doctor = DoctorFactory()
    client = APIClient()
    client.force_authenticate(user=other_doctor.user)
    resp = client.post(URL, _sample(belt), format="json")
    assert resp.status_code == 400
    assert "Not your belt" in resp.data["errors"][0]["detail"]


def test_query_raw_and_hourly(parent_client, baby, belt):
    now = timezone.now()
    for i in range(6):
        MeasurementFactory(
            baby=baby, belt=belt,
            heart_rate=120 + i, recorded_at=now - timedelta(minutes=10 * i),
        )
    resp = parent_client.get(URL, {"baby_id": baby.id})
    assert resp.status_code == 200
    assert resp.data["count"] == 6

    resp = parent_client.get(URL, {"baby_id": baby.id, "granularity": "hour"})
    assert resp.status_code == 200
    assert len(resp.data["results"]) >= 1
    first = resp.data["results"][0]
    assert first["count"] >= 1 and first["heart_rate_avg"] is not None


def test_bucket_includes_battery_and_respiration_averages(parent_client, baby, belt):
    now = timezone.now()
    for i in range(3):
        MeasurementFactory(
            baby=baby, belt=belt,
            battery=90 - i, respiratory_rate=40 + i,
            recorded_at=now - timedelta(minutes=i),
        )
    resp = parent_client.get(URL, {"baby_id": baby.id, "granularity": "hour"})
    assert resp.status_code == 200
    bucket = resp.data["results"][0]
    assert bucket["battery_avg"] is not None
    assert bucket["respiratory_rate_avg"] == 41.0
    assert "movement_magnitude_avg" not in bucket


def test_query_requires_owned_baby(parent_client, baby):
    from tests.factories import BabyFactory

    foreign = BabyFactory()
    resp = parent_client.get(URL, {"baby_id": foreign.id})
    assert resp.status_code == 404


def test_ingest_resolves_open_no_data_alert(parent_client, baby, belt):
    Alert.objects.create(
        baby=baby, belt=belt, type=Alert.Type.NO_DATA,
        severity=Alert.Severity.WARNING, message="x", triggered_at=timezone.now(),
    )
    parent_client.post(URL, _sample(belt), format="json")
    assert not Alert.objects.filter(type=Alert.Type.NO_DATA, resolved_at__isnull=True).exists()
