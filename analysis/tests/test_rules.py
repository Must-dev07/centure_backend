"""Rule-engine unit tests: every rule from Section 5, dedup, no-data watchdog."""
from datetime import timedelta

import pytest
from django.utils import timezone

from alerts.models import Alert
from analysis.rules import RULES, run_rules
from analysis.tasks import detect_no_data
from tests.factories import MeasurementFactory

pytestmark = pytest.mark.django_db


def make_measurement(baby, bracelet, **kw):
    return MeasurementFactory(baby=baby, bracelet=bracelet, **kw)


@pytest.mark.parametrize(
    "field,value,alert_type,severity",
    [
        ("temperature", 39.2, "high_temp", "critical"),
        ("temperature", 35.0, "low_temp", "warning"),
        ("spo2", 88.0, "low_oxygen", "critical"),
        ("heart_rate", 200.0, "high_hr", "critical"),
        ("heart_rate", 70.0, "low_hr", "critical"),
        ("battery", 10.0, "battery_low", "info"),
    ],
)
def test_threshold_rules(baby, bracelet, field, value, alert_type, severity):
    m = make_measurement(baby, bracelet, **{field: value})
    alerts = run_rules(m)
    types = {a.type for a in alerts}
    assert alert_type in types
    alert = next(a for a in alerts if a.type == alert_type)
    assert alert.severity == severity
    assert alert.value == value
    # Non-diagnostic wording (Section 0 rule 10)
    assert "diagnos" not in alert.message.lower() or "not a" in alert.message.lower()


def test_normal_measurement_triggers_nothing(baby, bracelet):
    m = make_measurement(baby, bracelet)
    assert run_rules(m) == []


def test_bracelet_removed_rule(baby, bracelet):
    m = make_measurement(baby, bracelet, skin_contact=False)
    types = {a.type for a in run_rules(m)}
    assert "bracelet_removed" in types


def test_no_movement_rule_needs_sustained_stillness(baby, bracelet):
    now = timezone.now()
    still = {"accel": [0, 0, 9.8], "gyro": [0, 0, 0], "magnitude": 0.0}
    # Only 2 still readings → not enough
    m1 = make_measurement(baby, bracelet, movement=still, recorded_at=now - timedelta(minutes=5))
    m2 = make_measurement(baby, bracelet, movement=still, recorded_at=now)
    assert "no_movement" not in {a.type for a in run_rules(m2)}
    # Third still reading in the window → fires
    m3 = make_measurement(baby, bracelet, movement=still, recorded_at=now + timedelta(seconds=1))
    assert "no_movement" in {a.type for a in run_rules(m3)}


def test_dedup_no_alert_storm(baby, bracelet):
    m1 = make_measurement(baby, bracelet, temperature=39.5)
    run_rules(m1)
    m2 = make_measurement(baby, bracelet, temperature=39.6)
    run_rules(m2)
    assert Alert.objects.filter(type="high_temp").count() == 1  # deduplicated

    # After resolution, the rule may fire again
    Alert.objects.filter(type="high_temp").update(resolved_at=timezone.now())
    m3 = make_measurement(baby, bracelet, temperature=39.7)
    run_rules(m3)
    assert Alert.objects.filter(type="high_temp").count() == 2


def test_critical_only_filter(baby, bracelet):
    m = make_measurement(baby, bracelet, temperature=39.5, spo2=85.0)
    alerts = run_rules(m, critical_only=True)
    types = {a.type for a in alerts}
    assert "low_oxygen" in types          # critical rule ran
    assert "high_temp" not in types       # non-critical deferred


def test_detect_no_data_task(baby, bracelet):
    bracelet.last_seen_at = timezone.now() - timedelta(minutes=30)
    bracelet.save(update_fields=["last_seen_at"])
    created = detect_no_data()
    assert created == 1
    assert Alert.objects.filter(type="no_data", resolved_at__isnull=True).exists()
    # Idempotent while alert is open
    assert detect_no_data() == 0


def test_rule_registry_is_pluggable():
    # All Section-5 per-measurement rules are registered
    from analysis import rules as r

    names = {type(rule).__name__ for rule in RULES}
    assert {
        "HighTemperatureRule", "LowTemperatureRule", "LowOxygenRule",
        "HighHeartRateRule", "LowHeartRateRule", "NoMovementRule",
        "BraceletRemovedRule", "BatteryLowRule",
    } <= names
