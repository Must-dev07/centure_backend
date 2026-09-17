"""JWT auth endpoints with Session-table refresh rotation & revocation.

Flow:
- login  -> issue access+refresh, record Session(refresh_jti)
- refresh-> verify token AND active Session row, revoke old row, create new one
- logout -> revoke Session row (refresh token becomes unusable immediately)
"""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Session
from .serializers import LoginSerializer, LogoutSerializer, RefreshSerializer, RegisterSerializer
from notifications.models import Notification
from notifications.utils import notify
from users.serializers import UserSummarySerializer


class AuthThrottle(AnonRateThrottle):
    scope = "auth"  # 20/min by default — brute-force protection


def _issue_tokens(user, request) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role  # informational only; server re-checks DB role
    Session.objects.create(
        user=user,
        refresh_jti=refresh["jti"],
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:256],
        ip_address=request.META.get("REMOTE_ADDR"),
        expires_at=datetime.fromtimestamp(refresh["exp"], tz=dt_timezone.utc),
    )
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSummarySerializer(user).data,
    }


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        role_tip = {
            "parent": "Add your baby and pair a bracelet to get started.",
            "doctor": "Patients will appear once a parent requests you or an admin assigns you.",
        }.get(user.role, "Welcome aboard.")
        notify(
            user,
            "Welcome to Smart Bracelet Monitor",
            role_tip,
            category=Notification.Category.SYSTEM,
        )
        return Response(_issue_tokens(user, request), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"].lower(),
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active:
            return Response(
                {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
            )
        return Response(_issue_tokens(user, request))


class RefreshView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            old = RefreshToken(serializer.validated_data["refresh"])
        except TokenError:
            return Response({"detail": "Invalid refresh token."}, status=401)

        session = Session.objects.filter(refresh_jti=old["jti"]).first()
        if session is None or not session.is_active:
            return Response({"detail": "Session revoked."}, status=401)

        session.revoked_at = timezone.now()  # rotation: old refresh is dead
        session.save(update_fields=["revoked_at"])
        return Response(_issue_tokens(session.user, request))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
        except TokenError:
            return Response({"detail": "Invalid refresh token."}, status=400)
        Session.objects.filter(refresh_jti=token["jti"], user=request.user).update(
            revoked_at=timezone.now()
        )
        return Response({"detail": "Logged out."})
