from rest_framework import serializers

from bracelets.models import Bracelet
from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    baby_name = serializers.CharField(source="baby.name", read_only=True)
    acknowledged_by_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()
    disclaimer = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = [
            "id", "baby", "baby_name", "bracelet", "type", "severity", "message",
            "value", "triggered_at", "resolved_at", "resolved_by", "resolved_by_name",
            "acknowledged_by", "acknowledged_by_name", "acknowledged_at",
            "auto_resolves_on_acknowledge", "disclaimer",
        ]
        read_only_fields = fields

    def get_acknowledged_by_name(self, obj) -> str | None:
        return obj.acknowledged_by.get_full_name() if obj.acknowledged_by_id else None

    def get_resolved_by_name(self, obj) -> str | None:
        return obj.resolved_by.get_full_name() if obj.resolved_by_id else None

    def get_disclaimer(self, obj) -> str:
        # Section 0 rule 10 — surfaced with every alert payload.
        return (
            "This alert flags an abnormal reading for caregiver or medical "
            "follow-up. It is not a medical diagnosis."
        )


class BleLostReportSerializer(serializers.Serializer):
    bracelet_id = serializers.PrimaryKeyRelatedField(
        queryset=Bracelet.objects.all(), source="bracelet"
    )
