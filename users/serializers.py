from rest_framework import serializers

from .models import Doctor, Parent, User


class UserSummarySerializer(serializers.ModelSerializer):
    doctor_profile_id = serializers.SerializerMethodField()
    parent_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "phone", "created_at",
            "doctor_profile_id", "parent_profile_id",
        ]
        read_only_fields = ["id", "email", "role", "created_at"]

    def get_doctor_profile_id(self, obj):
        return getattr(getattr(obj, "doctor_profile", None), "id", None)

    def get_parent_profile_id(self, obj):
        return getattr(getattr(obj, "parent_profile", None), "id", None)


class DoctorSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer()

    class Meta:
        model = Doctor
        fields = ["id", "user", "license_number", "specialty"]

    def update(self, instance, validated):
        user_data = validated.pop("user", {})
        for field in ("first_name", "last_name", "phone"):
            if field in user_data:
                setattr(instance.user, field, user_data[field])
        instance.user.save()
        return super().update(instance, validated)


class ParentSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer()

    class Meta:
        model = Parent
        fields = ["id", "user", "address", "emergency_contact"]

    def update(self, instance, validated):
        user_data = validated.pop("user", {})
        for field in ("first_name", "last_name", "phone"):
            if field in user_data:
                setattr(instance.user, field, user_data[field])
        instance.user.save()
        return super().update(instance, validated)
