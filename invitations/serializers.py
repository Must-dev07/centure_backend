from rest_framework import serializers

from babies.models import Baby
from .models import Invitation


class InvitationBabySerializer(serializers.ModelSerializer):
    class Meta:
        model = Baby
        fields = ["id", "name"]


class InvitationSerializer(serializers.ModelSerializer):
    """Listing representation. Never exposes `token` (a credential, like a
    password-reset link) nor the shareable link built from it."""

    babies = InvitationBabySerializer(many=True, read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id", "email", "first_name", "last_name", "phone", "status",
            "created_by", "created_at", "expires_at", "accepted_at", "babies",
        ]
        read_only_fields = fields


class InvitationAcceptSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
