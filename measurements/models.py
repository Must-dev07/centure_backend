"""Measurement: write-heavy time-series table, indexed on (baby, recorded_at)."""
from django.db import models

from babies.models import Baby
from bracelets.models import Bracelet


class Measurement(models.Model):
    baby = models.ForeignKey(Baby, on_delete=models.CASCADE, related_name="measurements")
    bracelet = models.ForeignKey(Bracelet, on_delete=models.CASCADE, related_name="measurements")
    heart_rate = models.FloatField(null=True, blank=True)       # bpm
    temperature = models.FloatField(null=True, blank=True)      # °C
    spo2 = models.FloatField(null=True, blank=True)             # %
    movement = models.JSONField(null=True, blank=True)          # {"accel":[x,y,z],"gyro":[x,y,z],"magnitude":f}
    battery = models.FloatField(null=True, blank=True)          # %
    skin_contact = models.BooleanField(default=True)
    recorded_at = models.DateTimeField(db_index=True)           # device timestamp
    received_at = models.DateTimeField(auto_now_add=True)       # server timestamp

    class Meta:
        indexes = [
            models.Index(fields=["baby", "recorded_at"], name="meas_baby_recorded_idx"),
        ]
        ordering = ["-recorded_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"Measurement baby={self.baby_id} at {self.recorded_at}"
