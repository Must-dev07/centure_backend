from rest_framework import serializers

from babies.models import Baby
from .models import Bracelet, Pairing


class BraceletSerializer(serializers.ModelSerializer):
    baby_name = serializers.CharField(source="baby.name", read_only=True, default=None)

    class Meta:
        model = Bracelet
        fields = [
            "id", "serial_number", "nickname", "firmware_version", "baby", "baby_name",
            "battery_level", "last_seen_at", "status", "created_at",
        ]
        read_only_fields = ["id", "baby", "last_seen_at", "created_at"]

    def validate_battery_level(self, value):
        if value is not None and not (0 <= value <= 100):
            raise serializers.ValidationError("Battery level must be 0–100.")
        return value


class PairingSerializer(serializers.ModelSerializer):
    baby_name = serializers.CharField(source="baby.name", read_only=True)

    class Meta:
        model = Pairing
        fields = ["id", "bracelet", "baby", "baby_name", "paired_at", "unpaired_at"]


class PairRequestSerializer(serializers.Serializer):
    baby_id = serializers.PrimaryKeyRelatedField(queryset=Baby.objects.all(), source="baby")
