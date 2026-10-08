"""Context-aware vital-sign classification (older child). Pure functions — no
database — so the thresholds can be unit-tested at their exact boundaries.

Every threshold comes from settings.ANALYSIS_THRESHOLDS (the single source
of truth). The mobile app mirrors these tables in
lib/core/vitals_classifier.dart for its live tile colours.

Context comes from the measurement's `activity`, which the app derives from
the belt's movement data:
  calm    — sleep / rest
  active  — effort, or recovery (the minutes right after effort, while heart
            rate and breathing are still coming down)
  unknown — no movement data (no IMU fitted): elevated-but-plausible values
            are only `info`; critical limits are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

NORMAL, INFO, WARNING, CRITICAL = "normal", "info", "warning", "critical"
RANK = {NORMAL: 0, INFO: 1, WARNING: 2, CRITICAL: 3}

HIGH, LOW = "high", "low"

CALM, ACTIVE, UNKNOWN = "calm", "active", "unknown"
_CONTEXT = {"sleep": CALM, "rest": CALM, "effort": ACTIVE, "recovery": ACTIVE}
CONTEXT_LABEL = {CALM: "at rest", ACTIVE: "after effort", UNKNOWN: "(activity unknown)"}


def context_for(activity: Optional[str]) -> str:
    return _CONTEXT.get(activity or "", UNKNOWN)


def _all(severity: str) -> dict:
    return {CALM: severity, ACTIVE: severity, UNKNOWN: severity}


@dataclass(frozen=True)
class Threshold:
    direction: str             # HIGH: value above limit, LOW: value below limit
    key: str                   # ANALYSIS_THRESHOLDS key holding the limit
    severity: dict             # context -> severity; missing context = normal
    inclusive: bool = False    # >= / <= instead of > / <


# Most extreme limit first, per direction.
HEART_RATE = (
    Threshold(HIGH, "HR_CRITICAL_HIGH_BPM", _all(CRITICAL)),
    Threshold(HIGH, "HR_EFFORT_HIGH_BPM", _all(WARNING)),
    Threshold(HIGH, "HR_REST_HIGH_BPM", {CALM: WARNING, UNKNOWN: INFO}),
    Threshold(LOW, "HR_CRITICAL_LOW_BPM", _all(CRITICAL)),
    Threshold(LOW, "HR_WARN_LOW_BPM", _all(WARNING)),
)
RESPIRATION = (
    Threshold(HIGH, "RESP_CRITICAL_HIGH_BRPM", _all(CRITICAL)),
    Threshold(HIGH, "RESP_EFFORT_HIGH_BRPM", {CALM: CRITICAL, ACTIVE: WARNING, UNKNOWN: WARNING}),
    Threshold(HIGH, "RESP_REST_HIGH_BRPM", {CALM: WARNING, UNKNOWN: INFO}),
    Threshold(LOW, "RESP_CRITICAL_LOW_BRPM", _all(CRITICAL)),
    Threshold(LOW, "RESP_WARN_LOW_BRPM", _all(WARNING)),
)
TEMPERATURE = (
    Threshold(HIGH, "TEMP_CRITICAL_HIGH_C", _all(CRITICAL), inclusive=True),
    Threshold(HIGH, "TEMP_FEVER_C", _all(WARNING), inclusive=True),
    Threshold(HIGH, "TEMP_INFO_HIGH_C", _all(INFO)),
    Threshold(LOW, "TEMP_CRITICAL_LOW_C", _all(CRITICAL)),
    Threshold(LOW, "TEMP_WARN_LOW_C", _all(WARNING)),
)
BATTERY = (
    Threshold(LOW, "BATTERY_WARN_PCT", _all(WARNING)),
    Threshold(LOW, "BATTERY_INFO_PCT", _all(INFO)),
)


@dataclass(frozen=True)
class Classification:
    severity: str = NORMAL
    direction: Optional[str] = None
    # Limit crossed for each severity reached (most extreme one per level).
    limits: dict = field(default_factory=dict)

    @property
    def limit(self) -> Optional[float]:
        return self.limits.get(self.severity)


OK = Classification()


def _crosses(th: Threshold, value: float, limit: float) -> bool:
    if th.direction == HIGH:
        return value >= limit if th.inclusive else value > limit
    return value <= limit if th.inclusive else value < limit


def classify(table: Sequence[Threshold], value: Optional[float],
             activity: Optional[str], t: dict) -> Classification:
    """Instantaneous classification of one reading."""
    if value is None:
        return OK
    ctx = context_for(activity)
    severity, direction, limits = NORMAL, None, {}
    for th in table:
        level = th.severity.get(ctx, NORMAL)
        limit = t[th.key]
        if level == NORMAL or not _crosses(th, value, limit):
            continue
        limits.setdefault(level, limit)
        if RANK[level] > RANK[severity]:
            severity, direction = level, th.direction
    return Classification(severity, direction, limits) if direction else OK


def persisted(readings: Sequence[Classification], required: dict) -> Classification:
    """Severity that has actually persisted. `readings` is newest first
    (current reading at index 0). Level L counts only when the newest
    `required[L]` readings are all at least L, in the current reading's
    direction. Falls back to lower levels, so one 190 bpm reading after two
    165s is a warning, not a critical alert."""
    if not readings or readings[0].direction is None:
        return OK
    direction = readings[0].direction
    for level in (CRITICAL, WARNING, INFO):
        n = max(1, int(required[level]))
        streak = readings[:n]
        if len(streak) == n and all(
            r.direction == direction and RANK[r.severity] >= RANK[level] for r in streak
        ):
            limit = next((r.limits[level] for r in streak if level in r.limits), None)
            return Classification(level, direction, {level: limit})
    return OK


def required_readings(t: dict, critical_needs_more: bool) -> dict:
    n = int(t["PERSIST_READINGS"])
    return {
        INFO: n,
        WARNING: n,
        CRITICAL: int(t["PERSIST_CRITICAL_READINGS"]) if critical_needs_more else n,
    }
