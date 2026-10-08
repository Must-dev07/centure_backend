"""Invitation endpoints (REFONTE §3.3 + owner decisions):

- GET  /invitations/?status=pending   doctor/admin: invitations in scope (no token)
- POST /invitations/{id}/resend/      doctor/admin: new token + 7-day validity
- POST /invitations/{token}/accept/   public (token only): create or link the
                                      parent account, attach the babies, log in

Doctor scope: invitations they created or that include a baby assigned to them
(consistent with doctors only accessing their assigned babies). Admins: all.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.views import AuthThrottle, _issue_tokens
from common.permissions import IsDoctorOrAdmin
from users.models import Parent, User
from .models import Invitation
from .serializers import InvitationAcceptSerializer, InvitationSerializer
from .services import invitation_link, renew_invitation


def invitations_for(user):
    qs = Invitation.objects.select_related("created_by").prefetch_related("babies")
    if user.role == "admin":
        return qs
    return qs.filter(Q(created_by=user) | Q(babies__assigned_doctor__user=user)).distinct()


class InvitationListView(generics.ListAPIView):
    serializer_class = InvitationSerializer
    permission_classes = [IsDoctorOrAdmin]

    def get_queryset(self):
        qs = invitations_for(self.request.user).order_by("-created_at")
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class InvitationResendView(APIView):
    """"Renvoyer l'invitation": works on a pending or expired invitation. A new
    token is generated (the previous link stops working) and the invitation is
    pending again for INVITATION_TTL_DAYS. The new link is returned so the staff
    member can share it; nothing is emailed."""

    permission_classes = [IsDoctorOrAdmin]

    def post(self, request, pk):
        invitation = generics.get_object_or_404(invitations_for(request.user), pk=pk)
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
            if invitation.status == Invitation.Status.ACCEPTED:
                return Response(
                    {"detail": "This invitation has already been accepted."},
                    status=status.HTTP_409_CONFLICT,
                )
            renew_invitation(invitation)
        data = InvitationSerializer(invitation).data
        data["invitation_link"] = invitation_link(invitation)
        return Response(data)


class InvitationAcceptView(APIView):
    """Public: the token is the only credential (like a password-reset link).

    404 unknown token · 410 expired or no longer pending · 400 invalid payload or
    password · 401 wrong password for an existing parent account · 409 the email
    belongs to a doctor/admin account. On success the babies are attached to the
    new or existing parent and a JWT pair is returned exactly like /auth/login.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AuthThrottle]

    GONE = {"detail": "This invitation has expired or is no longer valid."}

    def post(self, request, token):
        invitation = Invitation.objects.filter(token=token).first()
        if invitation is None:
            return Response({"detail": "Invitation not found."}, status=status.HTTP_404_NOT_FOUND)
        if not self._is_acceptable(invitation):
            return Response(self.GONE, status=status.HTTP_410_GONE)

        serializer = InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
            if not self._is_acceptable(invitation):
                return Response(self.GONE, status=status.HTTP_410_GONE)

            existing = User.objects.filter(email__iexact=invitation.email).first()
            if existing is not None:
                if existing.role != User.Role.PARENT:
                    return Response(
                        {"detail": "This email belongs to an account that cannot accept a parent invitation."},
                        status=status.HTTP_409_CONFLICT,
                    )
                user = authenticate(request, username=existing.email, password=data["password"])
                if user is None or not user.is_active:
                    return Response(
                        {"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED
                    )
                # Existing parent account: linked, never duplicated or overwritten.
                parent, _ = Parent.objects.get_or_create(user=user)
            else:
                user = self._create_parent_user(invitation, data)
                parent = Parent.objects.create(user=user)

            invitation.babies.filter(parent__isnull=True).update(parent=parent)
            invitation.status = Invitation.Status.ACCEPTED
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["status", "accepted_at"])
            tokens = _issue_tokens(user, request)
        return Response(tokens)

    @staticmethod
    def _is_acceptable(invitation) -> bool:
        return invitation.status == Invitation.Status.PENDING and invitation.expires_at > timezone.now()

    @staticmethod
    def _create_parent_user(invitation, data):
        first_name = data.get("first_name") or invitation.first_name
        last_name = data.get("last_name") or invitation.last_name
        phone = data.get("phone") or invitation.phone
        candidate = User(
            email=invitation.email, first_name=first_name, last_name=last_name, role=User.Role.PARENT
        )
        try:
            validate_password(data["password"], user=candidate)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)})
        return User.objects.create_user(
            email=invitation.email,
            password=data["password"],
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=User.Role.PARENT,
        )
