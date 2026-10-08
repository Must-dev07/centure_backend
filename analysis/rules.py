"""Pluggable rule engine (Section 4.4).

Adding a rule = one new Rule subclass + one @register line. Rules marked
`critical=True` run synchronously on ingest (HR/respiration — latency-critical);
the rest run in a Celery task right after ingest.

Vital-sign rules are context-aware and persistent (analysis/classifier.py):
severity depends on the measurement's activity, and a level only fires once
enough consecutive recent readings reach it — one noisy sample never does.

Deduplication: a rule does not re-fire while an unresolved alert of the same
type and at least the same severity exists for the same baby (prevents alert
storms on continuous streams); an escalation (e.g. fever warning → critical)
does raise a new alert.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.conf import settings

from alerts.models import Alert

from . import classifier as c


@dataclass
class RuleResult:
    type: str
    severity: str
    message: str
    value: Optional[float] = None


class Rule:
    """Base rule. Subclasses implement evaluate(measurement) -> RuleResult|None."""

    critical = False  # critical rules run synchronously on ingest

    def evaluate(self, measurement) -> Optional[RuleResult]:  # pragma: no cover
        raise NotImplementedError

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def thresholds() -> dict:
        return settings.ANALYSIS_THRESHOLDS


RULES: list[Rule] = []


def register(cls):
    """Class decorator: instantiate and register the rule."""
    RULES.append(cls())
    return cls


# ---------------------------------------------------------------------------
# Vital-sign rules. Messages use "flagged for follow-up" language, never
# diagnostic claims (Section 0, rule 10).
# ---------------------------------------------------------------------------

class VitalRule(Rule):
    """One direction (high or low) of one vital, classified with context and
    persistence. Subclasses only declare what they measure."""

    field: str
    table: tuple
    direction: str
    alert_type: str
    label: str
    unit: str
    decimals = 0
    # HR / respiration: a critical level must persist longer than a warning.
    critical_needs_more = False
    uses_activity = True

    def recent(self, m) -> list[tuple[float, Optional[str]]]:
        """(value, activity) of this reading plus the preceding ones of the
        same baby, newest first. Stops at a gap (value not measured)."""
        from measurements.models import Measurement

        t = self.thresholds()
        n = max(int(t["PERSIST_READINGS"]), int(t["PERSIST_CRITICAL_READINGS"]))
        since = m.recorded_at - timedelta(seconds=t["PERSIST_WINDOW_S"])
        rows = (
            Measurement.objects.filter(
                baby_id=m.baby_id, recorded_at__lte=m.recorded_at, recorded_at__gte=since
            )
            .exclude(pk=m.pk)
            .order_by("-recorded_at")
            .values_list(self.field, "activity")[: n - 1]
        )
        out = [(getattr(m, self.field), m.activity)]
        for value, activity in rows:
            if value is None:
                break
            out.append((value, activity))
        return out

    def evaluate(self, m):
        value = getattr(m, self.field)
        if value is None:
            return None
        t = self.thresholds()
        readings = [c.classify(self.table, v, a, t) for v, a in self.recent(m)]
        result = c.persisted(readings, c.required_readings(t, self.critical_needs_more))
        if result.severity == c.NORMAL or result.direction != self.direction:
            return None
        return RuleResult(self.alert_type, result.severity, self.message(m, value, result), value)

    def message(self, m, value, result) -> str:
        fmt = f"{{:.{self.decimals}f}}"
        where = f" {c.CONTEXT_LABEL[c.context_for(m.activity)]}" if self.uses_activity else ""
        side = "above" if self.direction == c.HIGH else "below"
        return (
            f"{self.label} {fmt.format(value)} {self.unit}{where} has stayed {side} "
            f"{fmt.format(result.limit)} {self.unit} ({result.severity}) — "
            "flagged for caregiver/medical follow-up."
        )


@register
class HighTemperatureRule(VitalRule):
    field, table, direction = "temperature", c.TEMPERATURE, c.HIGH
    alert_type, label, unit, decimals = Alert.Type.HIGH_TEMP, "Temperature", "°C", 1
    uses_activity = False


@register
class LowTemperatureRule(VitalRule):
    field, table, direction = "temperature", c.TEMPERATURE, c.LOW
    alert_type, label, unit, decimals = Alert.Type.LOW_TEMP, "Temperature", "°C", 1
    uses_activity = False


@register
class HighHeartRateRule(VitalRule):
    critical = True
    field, table, direction = "heart_rate", c.HEART_RATE, c.HIGH
    alert_type, label, unit = Alert.Type.HIGH_HR, "Heart rate", "bpm"
    critical_needs_more = True


@register
class LowHeartRateRule(VitalRule):
    critical = True
    field, table, direction = "heart_rate", c.HEART_RATE, c.LOW
    alert_type, label, unit = Alert.Type.LOW_HR, "Heart rate", "bpm"
    critical_needs_more = True


@register
class HighRespirationRule(VitalRule):
    critical = True
    field, table, direction = "respiratory_rate", c.RESPIRATION, c.HIGH
    alert_type, label, unit = Alert.Type.HIGH_RESP, "Respiratory rate", "breaths/min"
    critical_needs_more = True


@register
class LowRespirationRule(VitalRule):
    critical = True  # slow or absent breathing is latency-critical
    field, table, direction = "respiratory_rate", c.RESPIRATION, c.LOW
    alert_type, label, unit = Alert.Type.LOW_RESP, "Respiratory rate", "breaths/min"
    critical_needs_more = True


@register
class beltRemovedRule(Rule):
    def evaluate(self, m):
        if m.skin_contact is False:
            return RuleResult(
                Alert.Type.belt_REMOVED, Alert.Severity.WARNING,
                "Skin-contact sensor reports the belt may have been removed — "
                "monitoring is interrupted until it is repositioned.",
            )
        return None


@register
class BatteryLowRule(VitalRule):
    field, table, direction = "battery", c.BATTERY, c.LOW
    alert_type, label, unit = Alert.Type.BATTERY_LOW, "belt battery", "%"
    uses_activity = False

    def message(self, m, value, result) -> str:
        if result.severity == c.WARNING:
            return f"belt battery at {value:.0f}% — recharge now, monitoring will stop soon."
        return f"belt battery at {value:.0f}% — please recharge soon."


# NOTE: BLE_LOST is reported by the mobile app via POST /api/v1/alerts/report-ble-lost/
# (the backend cannot observe the BLE link). NO_DATA is produced by the
# analysis.tasks.detect_no_data Celery-beat task, not by a per-measurement rule.


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------

def _open_alert_covers(baby_id: int, alert_type: str, severity: str) -> bool:
    """An unresolved alert of this type at the same or a higher severity."""
    open_severities = Alert.objects.filter(
        baby_id=baby_id, type=alert_type, resolved_at__isnull=True
    ).values_list("severity", flat=True)
    return any(c.RANK[s] >= c.RANK[severity] for s in open_severities)


def _create_alert(measurement, result: RuleResult) -> Alert:
    alert = Alert.objects.create(
        baby_id=measurement.baby_id,
        belt_id=measurement.belt_id,
        type=result.type,
        severity=result.severity,
        message=result.message,
        value=result.value,
        triggered_at=measurement.recorded_at,
    )
    # Fan out notifications asynchronously (Celery; eager in tests).
    from notifications.tasks import dispatch_alert_notifications

    dispatch_alert_notifications.delay(alert.id)
    return alert


def run_rules(measurement, critical_only: bool = False, non_critical_only: bool = False) -> list[Alert]:
    """Evaluate registered rules against one measurement, create deduplicated alerts."""
    created: list[Alert] = []
    for rule in RULES:
        if critical_only and not rule.critical:
            continue
        if non_critical_only and rule.critical:
            continue
        result = rule.evaluate(measurement)
        if result and not _open_alert_covers(measurement.baby_id, result.type, result.severity):
            created.append(_create_alert(measurement, result))
    return created
