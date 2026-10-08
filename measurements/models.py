"""Measurement: write-heavy time-series table, indexed on (baby, recorded_at)."""
from django.db import models

from babies.models import Baby
from belts.models import belt


class Measurement(models.Model):
    class Activity(models.TextChoices):
        """Derived by the mobile app from the belt's movement data; gives
        the alert rules their context (analysis/classifier.py)."""

        SLEEP = "sleep"
        REST = "rest"
        EFFORT = "effort"
        RECOVERY = "recovery"  # just after effort, vitals still coming down
        UNKNOWN = "unknown"    # no movement data (no IMU fitted)

    baby =models.ForeignKey(Baby, on_delete=models.CASCADE, related_name="measurements")
    belt = models.ForeignKey(belt, on_delete=models.CASCADE, related_name="measurements")
    heart_rate = models.FloatField(null=True, blank=True)       # bpm
    temperature = models.FloatField(null=True, blank=True)      # °C
    respiratory_rate = models.FloatField(null=True, blank=True) # breaths/min
    battery = models.FloatField(null=True, blank=True)          # %
    skin_contact = models.BooleanField(default=True)
    activity = models.CharField(max_length=10, choices=Activity.choices, default=Activity.UNKNOWN)
    recorded_at = models.DateTimeField(db_index=True)           # device timestamp
    received_at = models.DateTimeField(auto_now_add=True)       # server timestamp

    class Meta:
        indexes = [
            models.Index(fields=["baby", "recorded_at"], name="meas_baby_recorded_idx"),
        ]
        ordering = ["-recorded_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Measurement baby={self.baby_id} at {self.recorded_at}"
