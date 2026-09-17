"""Auth serializers: register (parent or doctor), login, refresh, logout."""
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from users.models import Doctor, Parent, User


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=["parent", "doctor"])  # admin created via CLI only
    # doctor-only fields
    license_number = serializers.CharField(max_length=64, required=False, allow_blank=True)
    specialty = serializers.CharField(max_length=128, required=False, allow_blank=True)
    # parent-only fields
    address = serializers.CharField(max_length=255, required=False, allow_blank=True)
    emergency_contact = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if attrs["role"] == "doctor" and not attrs.get("license_number"):
            raise serializers.ValidationError(
                {"license_number": "Required for doctor accounts."}
            )
        return attrs

    def create(self, validated):
        user = User.objects.create_user(
            email=validated["email"],
            password=validated["password"],
            first_name=validated["first_name"],
            last_name=validated["last_name"],
            phone=validated.get("phone", ""),
            role=validated["role"],
        )
        if validated["role"] == "doctor":
            Doctor.objects.create(
                user=user,
                license_number=validated["license_number"],
                specialty=validated.get("specialty", ""),
            )
        else:
            Parent.objects.create(
                user=user,
                address=validated.get("address", ""),
                emergency_contact=validated.get("emergency_contact", ""),
            )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
