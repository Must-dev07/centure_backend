"""Measurement serializers with strict physiological range validation
(Section 7: reject impossible values like HR=-5 or 900)."""
from rest_framework import serializers

from .models import Measurement


class MeasurementIngestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = [
            "belt", "heart_rate", "temperature", "respiratory_rate",
            "battery", "skin_contact", "activity", "recorded_at",
        ]
        # Optional: older app versions don't send it → "unknown".
        extra_kwargs = {"activity": {"required": False}}

    def validate_heart_rate(self, v):
        if v is not None and not (20 <= v <= 300):
            raise serializers.ValidationError("Heart rate out of plausible range (20–300 bpm).")
        return v

    def validate_temperature(self, v):
        if v is not None and not (25 <= v <= 45):
            raise serializers.ValidationError("Temperature out of plausible range (25–45°C).")
        return v

    def validate_respiratory_rate(self, v):
        if v is not None and not (0 <= v <= 150):
            raise serializers.ValidationError(
                "Respiratory rate out of plausible range (0–150 breaths/min)."
            )
        return v

    def validate_battery(self, v):
        if v is not None and not (0 <= v <= 100):
            raise serializers.ValidationError("Battery must be 0–100%.")
        return v


class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = [
            "id", "baby", "belt", "heart_rate", "temperature", "respiratory_rate",
            "battery", "skin_contact", "activity", "recorded_at", "received_at",
        ]


class MeasurementBucketSerializer(serializers.Serializer):
    """Aggregated bucket for granularity != raw."""

    bucket = serializers.DateTimeField()
    heart_rate_avg = serializers.FloatField(allow_null=True)
    temperature_avg = serializers.FloatField(allow_null=True)
    respiratory_rate_avg = serializers.FloatField(allow_null=True)
    battery_avg = serializers.FloatField(allow_null=True)
    heart_rate_min = serializers.FloatField(allow_null=True)
    heart_rate_max = serializers.FloatField(allow_null=True)
    count = serializers.IntegerField()
