"""Ingest (single + bulk), validation, query & granularity tests."""
from datetime import timedelta

import pytest
from django.utils import timezone

from alerts.models import Alert
from measurements.models import Measurement
from tests.factories import MeasurementFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/measurements/"


def _sample(bracelet, **kw):
    base = {
        "bracelet": bracelet.id,
        "heart_rate": 130,
        "temperature": 37.0,
        "spo2": 98,
        "movement": {"accel": [0.1, 0.2, 9.8], "gyro": [0, 0, 0], "magnitude": 0.4},
        "battery": 80,
        "skin_contact": True,
        "recorded_at": timezone.now().isoformat(),
    }
    base.update(kw)
    return base


def test_single_ingest_updates_bracelet(parent_client, bracelet):
    resp = parent_client.post(URL, _sample(bracelet), format="json")
    assert resp.status_code == 201
    assert resp.data["created"] == 1
    bracelet.refresh_from_db()
    assert bracelet.last_seen_at is not None
    assert bracelet.battery_level == 80


def test_bulk_ingest(parent_client, bracelet):
    payload = [_sample(bracelet) for _ in range(10)]
    resp = parent_client.post(URL, payload, format="json")
    assert resp.status_code == 201
    assert resp.data["created"] == 10
    assert Measurement.objects.count() == 10


def test_ingest_rejects_impossible_values(parent_client, bracelet):
    resp = parent_client.post(URL, _sample(bracelet, heart_rate=-5), format="json")
    assert resp.status_code == 400
    resp = parent_client.post(URL, _sample(bracelet, heart_rate=900), format="json")
    assert resp.status_code == 400
    resp = parent_client.post(URL, _sample(bracelet, spo2=140), format="json")
    assert resp.status_code == 400


def test_ingest_rejects_unpaired_bracelet(parent_client, bracelet):
    bracelet.unpair()
    resp = parent_client.post(URL, _sample(bracelet), format="json")
    assert resp.status_code == 400
    assert resp.data["errors"][0]["detail"] == "Bracelet not paired."


def test_ingest_forbidden_on_foreign_bracelet(bracelet):
    # A doctor who is NOT the baby's assigned doctor → bracelet invisible
    from rest_framework.test import APIClient

    from tests.factories import DoctorFactory

    other_doctor = DoctorFactory()
    client = APIClient()
    client.force_authenticate(user=other_doctor.user)
    resp = client.post(URL, _sample(bracelet), format="json")
    assert resp.status_code == 400
    assert "Not your bracelet" in resp.data["errors"][0]["detail"]


def test_query_raw_and_hourly(parent_client, baby, bracelet):
    now = timezone.now()
    for i in range(6):
        MeasurementFactory(
            baby=baby, bracelet=bracelet,
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


def test_bucket_includes_battery_and_movement_averages(parent_client, baby, bracelet):
    now = timezone.now()
    for i in range(3):
        MeasurementFactory(
            baby=baby, bracelet=bracelet,
            battery=90 - i, movement={"magnitude": 0.5 + i * 0.1},
            recorded_at=now - timedelta(minutes=i),
        )
    resp = parent_client.get(URL, {"baby_id": baby.id, "granularity": "hour"})
    assert resp.status_code == 200
    bucket = resp.data["results"][0]
    assert bucket["battery_avg"] is not None
    assert bucket["movement_magnitude_avg"] is not None


def test_query_requires_owned_baby(parent_client, baby):
    from tests.factories import BabyFactory

    foreign = BabyFactory()
    resp = parent_client.get(URL, {"baby_id": foreign.id})
    assert resp.status_code == 404


def test_ingest_resolves_open_no_data_alert(parent_client, baby, bracelet):
    Alert.objects.create(
        baby=baby, bracelet=bracelet, type=Alert.Type.NO_DATA,
        severity=Alert.Severity.WARNING, message="x", triggered_at=timezone.now(),
    )
    parent_client.post(URL, _sample(bracelet), format="json")
    assert not Alert.objects.filter(type=Alert.Type.NO_DATA, resolved_at__isnull=True).exists()
