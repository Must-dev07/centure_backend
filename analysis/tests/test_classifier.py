"""Pure classifier tests: boundary values per context, persistence, and the
drift check against the mobile app's mirrored thresholds."""
import re
from pathlib import Path

import pytest
from django.conf import settings

from analysis import classifier as c

T = settings.ANALYSIS_THRESHOLDS


def sev(table, value, activity="rest"):
    return c.classify(table, value, activity, T).severity


@pytest.mark.parametrize(
    "value,activity,expected",
    [
        (60, "rest", "normal"), (100, "rest", "normal"), (100.5, "rest", "warning"),
        (130, "sleep", "warning"), (130, "effort", "normal"), (130, "recovery", "normal"),
        (160, "effort", "normal"), (161, "effort", "warning"), (161, "rest", "warning"),
        (180, "effort", "warning"), (181, "effort", "critical"),
        (130, "unknown", "info"), (130, None, "info"), (170, "unknown", "warning"),
        (50, "rest", "normal"), (49, "rest", "warning"), (49, "effort", "warning"),
        (40, "rest", "warning"), (39, "rest", "critical"),
    ],
)
def test_heart_rate(value, activity, expected):
    assert sev(c.HEART_RATE, value, activity) == expected


@pytest.mark.parametrize(
    "value,activity,expected",
    [
        (18, "rest", "normal"), (30, "rest", "normal"), (31, "rest", "warning"),
        (40, "rest", "warning"), (41, "rest", "critical"),
        (35, "effort", "normal"), (40, "effort", "normal"), (41, "effort", "warning"),
        (35, "unknown", "info"), (41, "unknown", "warning"),
        (50, "effort", "warning"), (51, "effort", "critical"), (51, "unknown", "critical"),
        (15, "sleep", "normal"), (12, "sleep", "normal"), (11, "sleep", "warning"),
        (8, "rest", "warning"), (7, "rest", "critical"), (0, "rest", "critical"),
    ],
)
def test_respiration(value, activity, expected):
    assert sev(c.RESPIRATION, value, activity) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (36.0, "normal"), (36.5, "normal"), (37.0, "normal"), (37.5, "normal"),
        (37.6, "info"), (37.9, "info"), (38.0, "warning"), (38.9, "warning"),
        (39.0, "critical"), (40.2, "critical"),
        (35.9, "warning"), (35.0, "warning"), (34.9, "critical"),
    ],
)
def test_temperature_ignores_activity(value, expected):
    for activity in ("rest", "effort", "unknown"):
        assert sev(c.TEMPERATURE, value, activity) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(100, "normal"), (20, "normal"), (19.9, "info"), (10, "info"), (9.9, "warning")],
)
def test_battery(value, expected):
    assert sev(c.BATTERY, value) == expected


def test_limit_reported_is_the_one_crossed():
    r = c.classify(c.HEART_RATE, 190, "rest", T)
    assert (r.severity, r.direction, r.limit) == ("critical", "high", 180)
    assert r.limits["warning"] == 160


# ------------------------------------------------------------- persistence
REQ = {"info": 3, "warning": 3, "critical": 6}


def readings(*pairs):
    """(value, activity) newest first → classifications."""
    return [c.classify(c.HEART_RATE, v, a, T) for v, a in pairs]


def test_persistence_needs_n_readings():
    assert c.persisted(readings((130, "rest"), (130, "rest")), REQ).severity == "normal"
    assert c.persisted(readings(*[(130, "rest")] * 3), REQ).severity == "warning"


def test_persistence_falls_back_to_lower_level():
    r = c.persisted(readings(*[(190, "effort")] * 5), REQ)
    assert (r.severity, r.limit) == ("warning", 160)
    assert c.persisted(readings(*[(190, "effort")] * 6), REQ).severity == "critical"


def test_one_spike_is_ignored():
    r = readings((200, "rest"), (85, "rest"), (85, "rest"), (85, "rest"))
    assert c.persisted(r, REQ).severity == "normal"


def test_streak_must_keep_direction():
    r = readings((30, "rest"), (190, "rest"), (30, "rest"))  # low, high, low
    assert c.persisted(r, REQ).severity == "normal"


def test_context_change_inside_streak():
    # Effort ends: 130 bpm is fine during recovery, a warning once at rest.
    r = readings((130, "rest"), (130, "rest"), (130, "recovery"))
    assert c.persisted(r, REQ).severity == "normal"
    r = readings((130, "rest"), (130, "unknown"), (130, "rest"))
    assert c.persisted(r, REQ).severity == "info"


def test_required_readings_from_settings():
    assert c.required_readings(T, critical_needs_more=True) == {
        "info": 3, "warning": 3, "critical": 6}
    assert c.required_readings(T, critical_needs_more=False)["critical"] == 3


# ------------------------------------------------------------- mirror drift
DART_MIRROR = (Path(settings.BASE_DIR).parent / "webapp" / "mobile" / "lib"
               / "core" / "vital_thresholds.dart")


def _camel(key: str) -> str:
    head, *rest = key.lower().split("_")
    return head + "".join(w.capitalize() for w in rest)


@pytest.mark.skipif(not DART_MIRROR.exists(), reason="mobile app not checked out alongside")
def test_mobile_mirror_matches_backend_thresholds():
    """The app's live tile colours must agree with the alerts the backend
    raises. Compares defaults (no env override in tests)."""
    source = DART_MIRROR.read_text(encoding="utf-8")
    consts = {
        name: float(value)
        for name, value in re.findall(r"static const (?:double|int) (\w+)\s*=\s*([\d.]+);", source)
    }
    for key, value in T.items():
        if key == "NO_DATA_MINUTES":
            continue  # backend-only watchdog
        assert consts.get(_camel(key)) == value, f"{key} differs in {DART_MIRROR.name}"
