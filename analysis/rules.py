"""Pluggable rule engine (Section 4.4).

Adding a rule = one new Rule subclass + one @register line. Rules marked
`critical=True` run synchronously on ingest (SpO2/HR — latency-critical);
the rest run in a Celery task right after ingest.

Deduplication: a rule does not re-fire while an unresolved alert of the same
type exists for the same baby (prevents alert storms on continuous streams).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.utils import timezone

from alerts.models import Alert


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
# Rules — Section 5 of the original spec. Messages use "flagged for follow-up"
# language, never diagnostic claims (Section 0, rule 10).
# ---------------------------------------------------------------------------

@register
class HighTemperatureRule(Rule):
    def evaluate(self, m):
        t = self.thresholds()["TEMP_HIGH_C"]
        if m.temperature is not None and m.temperature > t:
            return RuleResult(
                Alert.Type.HIGH_TEMP, Alert.Severity.CRITICAL,
                f"Temperature reading {m.temperature:.1f}°C is above {t}°C — "
                "flagged for caregiver/medical follow-up.",
                m.temperature,
            )
        return None


@register
class LowTemperatureRule(Rule):
    def evaluate(self, m):
        t = self.thresholds()["TEMP_LOW_C"]
        if m.temperature is not None and m.temperature < t:
            return RuleResult(
                Alert.Type.LOW_TEMP, Alert.Severity.WARNING,
                f"Temperature reading {m.temperature:.1f}°C is below {t}°C — "
                "flagged for caregiver/medical follow-up.",
                m.temperature,
            )
        return None


@register
class LowOxygenRule(Rule):
    critical = True  # SpO2 is latency-critical — evaluated synchronously

    def evaluate(self, m):
        t = self.thresholds()["SPO2_LOW_PCT"]
        if m.spo2 is not None and m.spo2 < t:
            return RuleResult(
                Alert.Type.LOW_OXYGEN, Alert.Severity.CRITICAL,
                f"SpO2 reading {m.spo2:.0f}% is below {t}% — "
                "flagged for caregiver/medical follow-up.",
                m.spo2,
            )
        return None


@register
class HighHeartRateRule(Rule):
    critical = True

    def evaluate(self, m):
        t = self.thresholds()["HR_HIGH_BPM"]
        if m.heart_rate is not None and m.heart_rate > t:
            return RuleResult(
                Alert.Type.HIGH_HR, Alert.Severity.CRITICAL,
                f"Heart rate reading {m.heart_rate:.0f} bpm is above {t} bpm — "
                "flagged for caregiver/medical follow-up.",
                m.heart_rate,
            )
        return None


@register
class LowHeartRateRule(Rule):
    critical = True

    def evaluate(self, m):
        t = self.thresholds()["HR_LOW_BPM"]
        if m.heart_rate is not None and m.heart_rate < t:
            return RuleResult(
                Alert.Type.LOW_HR, Alert.Severity.CRITICAL,
                f"Heart rate reading {m.heart_rate:.0f} bpm is below {t} bpm — "
                "flagged for caregiver/medical follow-up.",
                m.heart_rate,
            )
        return None


@register
class NoMovementRule(Rule):
    """Fires if the current measurement AND all measurements in the last
    NO_MOVEMENT_MINUTES window show near-zero movement magnitude."""

    MAGNITUDE_EPSILON = 0.05

    def evaluate(self, m):
        mag = (m.movement or {}).get("magnitude")
        if mag is None or mag > self.MAGNITUDE_EPSILON:
            return None
        window_min = self.thresholds()["NO_MOVEMENT_MINUTES"]
        since = m.recorded_at - timezone.timedelta(minutes=window_min)
        from measurements.models import Measurement

        window = Measurement.objects.filter(
            baby_id=m.baby_id, recorded_at__gte=since, recorded_at__lte=m.recorded_at
        ).values_list("movement", flat=True)[:500]
        readings = [w.get("magnitude") for w in window if w and w.get("magnitude") is not None]
        if len(readings) >= 3 and all(r <= self.MAGNITUDE_EPSILON for r in readings):
            return RuleResult(
                Alert.Type.NO_MOVEMENT, Alert.Severity.CRITICAL,
                f"No movement detected for {window_min:.0f} minutes — "
                "please check on the baby; flagged for follow-up.",
                mag,
            )
        return None


@register
class BraceletRemovedRule(Rule):
    def evaluate(self, m):
        if m.skin_contact is False:
            return RuleResult(
                Alert.Type.BRACELET_REMOVED, Alert.Severity.WARNING,
                "Skin-contact sensor reports the bracelet may have been removed — "
                "monitoring is interrupted until it is repositioned.",
            )
        return None


@register
class BatteryLowRule(Rule):
    def evaluate(self, m):
        t = self.thresholds()["BATTERY_LOW_PCT"]
        if m.battery is not None and m.battery < t:
            return RuleResult(
                Alert.Type.BATTERY_LOW, Alert.Severity.INFO,
                f"Bracelet battery at {m.battery:.0f}% — please recharge soon.",
                m.battery,
            )
        return None


# NOTE: BLE_LOST is reported by the mobile app via POST /api/v1/alerts/report-ble-lost/
# (the backend cannot observe the BLE link). NO_DATA is produced by the
# analysis.tasks.detect_no_data Celery-beat task, not by a per-measurement rule.


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------

def _open_alert_exists(baby_id: int, alert_type: str) -> bool:
    return Alert.objects.filter(
        baby_id=baby_id, type=alert_type, resolved_at__isnull=True
    ).exists()


def _create_alert(measurement, result: RuleResult) -> Alert:
    alert = Alert.objects.create(
        baby_id=measurement.baby_id,
        bracelet_id=measurement.bracelet_id,
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
        if result and not _open_alert_exists(measurement.baby_id, result.type):
            created.append(_create_alert(measurement, result))
    return created
