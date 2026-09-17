"""Measurement serializers with strict physiological range validation
(Section 7: reject impossible values like HR=-5 or 900)."""
from rest_framework import serializers

from .models import Measurement


class MovementSerializer(serializers.Serializer):
    accel = serializers.ListField(
        child=serializers.FloatField(), min_length=3, max_length=3, required=False
    )
    gyro = serializers.ListField(
        child=serializers.FloatField(), min_length=3, max_length=3, required=False
    )
    magnitude = serializers.FloatField(min_value=0, max_value=100, required=False)


class MeasurementIngestSerializer(serializers.ModelSerializer):
    movement = MovementSerializer(required=False, allow_null=True)

    class Meta:
        model = Measurement
        fields = [
            "bracelet", "heart_rate", "temperature", "spo2", "movement",
            "battery", "skin_contact", "recorded_at",
        ]

    def validate_heart_rate(self, v):
        if v is not None and not (20 <= v <= 300):
            raise serializers.ValidationError("Heart rate out of plausible range (20–300 bpm).")
        return v

    def validate_temperature(self, v):
        if v is not None and not (25 <= v <= 45):
            raise serializers.ValidationError("Temperature out of plausible range (25–45°C).")
        return v

    def validate_spo2(self, v):
        if v is not None and not (0 <= v <= 100):
            raise serializers.ValidationError("SpO2 must be 0–100%.")
        return v

    def validate_battery(self, v):
        if v is not None and not (0 <= v <= 100):
            raise serializers.ValidationError("Battery must be 0–100%.")
        return v


class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = [
            "id", "baby", "bracelet", "heart_rate", "temperature", "spo2",
            "movement", "battery", "skin_contact", "recorded_at", "received_at",
        ]


class MeasurementBucketSerializer(serializers.Serializer):
    """Aggregated bucket for granularity != raw."""

    bucket = serializers.DateTimeField()
    heart_rate_avg = serializers.FloatField(allow_null=True)
    temperature_avg = serializers.FloatField(allow_null=True)
    spo2_avg = serializers.FloatField(allow_null=True)
    battery_avg = serializers.FloatField(allow_null=True)
    movement_magnitude_avg = serializers.FloatField(allow_null=True)
    heart_rate_min = serializers.FloatField(allow_null=True)
    heart_rate_max = serializers.FloatField(allow_null=True)
    count = serializers.IntegerField()
