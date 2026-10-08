"""Rule-engine tests: context-aware vital rules with persistence, dedup /
escalation, no-data watchdog. Boundary values: test_classifier.py."""
from datetime import timedelta

import pytest
from django.utils import timezone

from alerts.models import Alert
from analysis.rules import RULES, run_rules
from analysis.tasks import detect_no_data
from tests.factories import MeasurementFactory

pytestmark = pytest.mark.django_db


def make_measurement(baby, belt, **kw):
    return MeasurementFactory(baby=baby, belt=belt, **kw)


def stream(baby, belt, n, start=None, step_s=5, **kw):
    """n readings at the firmware's 5 s cadence; rules run on each, like
    ingest does. Returns every alert created."""
    start = start or timezone.now() - timedelta(seconds=step_s * n)
    alerts = []
    for i in range(n):
        m = make_measurement(baby, belt, recorded_at=start + timedelta(seconds=step_s * i), **kw)
        alerts += run_rules(m)
    return alerts


@pytest.mark.parametrize(
    "fields,readings,alert_type,severity",
    [
        ({"temperature": 39.2}, 3, "high_temp", "critical"),
        ({"temperature": 38.4}, 3, "high_temp", "warning"),
        ({"temperature": 37.7}, 3, "high_temp", "info"),
        ({"temperature": 35.5}, 3, "low_temp", "warning"),
        ({"temperature": 34.8}, 3, "low_temp", "critical"),
        ({"respiratory_rate": 35.0, "activity": "rest"}, 3, "high_resp", "warning"),
        ({"respiratory_rate": 45.0, "activity": "rest"}, 6, "high_resp", "critical"),
        ({"respiratory_rate": 45.0, "activity": "effort"}, 6, "high_resp", "warning"),
        ({"respiratory_rate": 55.0, "activity": "effort"}, 6, "high_resp", "critical"),
        ({"respiratory_rate": 10.0}, 3, "low_resp", "warning"),
        ({"respiratory_rate": 5.0}, 6, "low_resp", "critical"),
        ({"heart_rate": 120.0, "activity": "rest"}, 3, "high_hr", "warning"),
        ({"heart_rate": 120.0, "activity": "unknown"}, 3, "high_hr", "info"),
        ({"heart_rate": 170.0, "activity": "effort"}, 3, "high_hr", "warning"),
        ({"heart_rate": 190.0, "activity": "effort"}, 6, "high_hr", "critical"),
        ({"heart_rate": 45.0, "activity": "rest"}, 3, "low_hr", "warning"),
        ({"heart_rate": 35.0, "activity": "rest"}, 6, "low_hr", "critical"),
        ({"battery": 15.0}, 3, "battery_low", "info"),
        ({"battery": 8.0}, 3, "battery_low", "warning"),
    ],
)
def test_threshold_rules(baby, belt, fields, readings, alert_type, severity):
    alerts = [a for a in stream(baby, belt, readings, **fields) if a.type == alert_type]
    assert alerts, f"no {alert_type} alert"
    assert max(alerts, key=lambda a: a.triggered_at).severity == severity
    # Non-diagnostic wording (Section 0 rule 10)
    for a in alerts:
        assert "diagnos" not in a.message.lower()
        assert len(a.message) <= 255


def test_normal_measurement_triggers_nothing(baby, belt):
    assert stream(baby, belt, 6) == []


def test_effort_values_are_normal_after_effort_but_not_at_rest(baby, belt):
    start = timezone.now() - timedelta(minutes=10)
    assert stream(baby, belt, 6, start=start, heart_rate=145.0,
                  respiratory_rate=36.0, activity="effort") == []
    assert stream(baby, belt, 6, start=start + timedelta(minutes=5), heart_rate=145.0,
                  respiratory_rate=36.0, activity="recovery") == []
    types = {a.type for a in stream(baby, belt, 3, heart_rate=145.0,
                                    respiratory_rate=36.0, activity="rest")}
    assert types == {"high_hr", "high_resp"}


def test_single_noisy_reading_raises_nothing(baby, belt):
    start = timezone.now() - timedelta(minutes=1)
    stream(baby, belt, 4, start=start)
    m = make_measurement(baby, belt, heart_rate=200.0, respiratory_rate=60.0,
                         temperature=39.5, recorded_at=start + timedelta(seconds=25))
    assert run_rules(m) == []


def test_critical_needs_longer_persistence_than_warning(baby, belt):
    alerts = stream(baby, belt, 5, heart_rate=190.0, activity="effort")
    assert {a.severity for a in alerts} == {"warning"}   # 3–5 readings: warning only
    m = make_measurement(baby, belt, heart_rate=190.0, activity="effort")
    assert [a.severity for a in run_rules(m)] == ["critical"]  # 6th reading escalates


def test_gap_breaks_the_streak(baby, belt):
    start = timezone.now() - timedelta(minutes=20)
    stream(baby, belt, 2, start=start, temperature=38.5)
    # Third fever reading arrives long after the window → no persistence.
    m = make_measurement(baby, belt, temperature=38.5, recorded_at=timezone.now())
    assert run_rules(m) == []


def test_missing_value_breaks_the_streak(baby, belt):
    start = timezone.now() - timedelta(minutes=1)
    stream(baby, belt, 2, start=start, temperature=38.5)
    make_measurement(baby, belt, temperature=None, recorded_at=start + timedelta(seconds=10))
    m = make_measurement(baby, belt, temperature=38.5, recorded_at=start + timedelta(seconds=15))
    assert run_rules(m) == []


def test_belt_removed_rule(baby, belt):
    m = make_measurement(baby, belt, skin_contact=False)
    types = {a.type for a in run_rules(m)}
    assert "belt_removed" in types


def test_dedup_no_alert_storm(baby, belt):
    stream(baby, belt, 6, temperature=39.5)
    assert Alert.objects.filter(type="high_temp").count() == 1  # deduplicated

    # After resolution, the rule may fire again
    Alert.objects.filter(type="high_temp").update(resolved_at=timezone.now())
    stream(baby, belt, 1, temperature=39.7)
    assert Alert.objects.filter(type="high_temp").count() == 2


def test_escalation_raises_new_alert(baby, belt):
    start = timezone.now() - timedelta(minutes=2)
    stream(baby, belt, 3, start=start, temperature=37.8)                          # info
    stream(baby, belt, 3, start=start + timedelta(seconds=15), temperature=38.3)  # warning
    stream(baby, belt, 3, start=start + timedelta(seconds=30), temperature=39.1)  # critical
    severities = list(Alert.objects.filter(type="high_temp")
                      .order_by("triggered_at").values_list("severity", flat=True))
    assert severities == ["info", "warning", "critical"]


def test_critical_only_filter(baby, belt):
    alerts = []
    start = timezone.now() - timedelta(minutes=1)
    for i in range(6):
        m = make_measurement(baby, belt, temperature=39.5, respiratory_rate=5.0,
                             recorded_at=start + timedelta(seconds=5 * i))
        alerts += run_rules(m, critical_only=True)
    types = {a.type for a in alerts}
    assert "low_resp" in types            # critical rule ran
    assert "high_temp" not in types       # non-critical deferred


def test_detect_no_data_task(baby, belt):
    belt.last_seen_at = timezone.now() - timedelta(minutes=30)
    belt.save(update_fields=["last_seen_at"])
    created = detect_no_data()
    assert created == 1
    assert Alert.objects.filter(type="no_data", resolved_at__isnull=True).exists()
    # Idempotent while alert is open
    assert detect_no_data() == 0


def test_rule_registry_is_pluggable():
    names = {type(rule).__name__ for rule in RULES}
    assert {
        "HighTemperatureRule", "LowTemperatureRule",
        "HighHeartRateRule", "LowHeartRateRule",
        "HighRespirationRule", "LowRespirationRule",
        "beltRemovedRule", "BatteryLowRule",
    } <= names
