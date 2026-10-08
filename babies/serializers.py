from django.utils import timezone
from rest_framework import serializers

from users.models import Doctor
from .models import Baby, DoctorAssignmentRequest, MedicalHistoryEntry


class MedicalHistoryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalHistoryEntry
        fields = ["id", "title", "details", "recorded_by", "supersedes", "created_at"]
        read_only_fields = ["id", "recorded_by", "created_at"]


class BabySerializer(serializers.ModelSerializer):
    medical_history = MedicalHistoryEntrySerializer(many=True, read_only=True)
    assigned_doctor = serializers.PrimaryKeyRelatedField(
        queryset=Doctor.objects.all(), required=False, allow_null=True
    )
    parent_name = serializers.CharField(source="parent.user.get_full_name", read_only=True, default="")

    class Meta:
        model = Baby
        fields = [
            "id", "name", "birth_date", "weight_grams", "height_cm", "gender",
            "parent", "parent_name", "assigned_doctor",
            "enrollment_reason", "enrollment_notes", "gestational_age_weeks", "enrolled_by",
            "medical_history", "created_at",
        ]
        read_only_fields = ["id", "parent", "enrolled_by", "created_at"]

    def validate_birth_date(self, value):
        if value > timezone.now().date():
            raise serializers.ValidationError("Birth date cannot be in the future.")
        return value

    def validate_weight_grams(self, value):
        # Plausibility bounds for newborn weight
        if not (300 <= value <= 8000):
            raise serializers.ValidationError("Weight must be between 300g and 8000g.")
        return value

    def validate_height_cm(self, value):
        # Plausibility bounds for a monitored newborn/infant
        if value is not None and not (20 <= value <= 120):
            raise serializers.ValidationError("Height must be between 20 cm and 120 cm.")
        return value

    def validate(self, attrs):
        # REFONTE §2.1: the "other" enrollment reason requires a description.
        reason = attrs.get("enrollment_reason", getattr(self.instance, "enrollment_reason", None))
        notes = attrs.get("enrollment_notes", getattr(self.instance, "enrollment_notes", ""))
        if reason == Baby.EnrollmentReason.OTHER and not (notes or "").strip():
            raise serializers.ValidationError(
                {"enrollment_notes": "A description is required when the enrollment reason is 'other'."}
            )
        return attrs


class BabyEnrollmentSerializer(BabySerializer):
    """POST /babies/ payload (REFONTE §3.1): the baby fields plus the parent's
    email, used to link an existing parent or invite a new one."""

    parent_email = serializers.EmailField(write_only=True)

    class Meta(BabySerializer.Meta):
        fields = BabySerializer.Meta.fields + ["parent_email"]


class DoctorAssignmentRequestSerializer(serializers.ModelSerializer):
    baby_name = serializers.CharField(source="baby.name", read_only=True)
    doctor_name = serializers.CharField(source="doctor.user.get_full_name", read_only=True)
    doctor_specialty = serializers.CharField(source="doctor.specialty", read_only=True)

    class Meta:
        model = DoctorAssignmentRequest
        fields = [
            "id", "baby", "baby_name", "doctor", "doctor_name", "doctor_specialty",
            "requested_by", "status", "note", "created_at", "responded_at",
        ]
        read_only_fields = [
            "id", "baby_name", "doctor_name", "doctor_specialty",
            "baby", "requested_by", "status", "created_at", "responded_at",
        ]
