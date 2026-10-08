"""Invitation creation/renewal helpers shared by baby enrollment (POST /babies/)
and the invitation endpoints. Invitations are delivered manually: the enrolling
doctor/admin receives an `app://invite/{token}` link and sends it to the parent
(no email infrastructure)."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Invitation

INVITATION_LINK_PREFIX = "app://invite/"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_token() -> str:
    # token_urlsafe(32) -> 43 URL-safe characters (fits max_length=64).
    while True:
        token = secrets.token_urlsafe(32)
        if not Invitation.objects.filter(token=token).exists():
            return token


def invitation_expiry(now=None):
    return (now or timezone.now()) + timedelta(days=settings.INVITATION_TTL_DAYS)


def invitation_link(invitation: Invitation) -> str:
    return f"{INVITATION_LINK_PREFIX}{invitation.token}"


def invite_parent_for_baby(*, email: str, baby, created_by) -> Invitation:
    """Attach `baby` to the still-valid pending invitation for `email`, or create
    a new one. A pending invitation already past its expiry (watchdog not run
    yet) is marked expired rather than reused, so callers never get a dead link.
    Must be called inside a transaction."""
    email = normalize_email(email)
    now = timezone.now()
    pending = list(
        Invitation.objects.select_for_update()
        .filter(email__iexact=email, status=Invitation.Status.PENDING)
        .order_by("-created_at")
    )
    stale = [inv.pk for inv in pending if inv.expires_at <= now]
    if stale:
        Invitation.objects.filter(pk__in=stale).update(status=Invitation.Status.EXPIRED)
    invitation = next((inv for inv in pending if inv.expires_at > now), None)
    if invitation is None:
        invitation = Invitation.objects.create(
            email=email,
            token=generate_token(),
            created_by=created_by,
            expires_at=invitation_expiry(now),
        )
    invitation.babies.add(baby)
    return invitation


def renew_invitation(invitation: Invitation) -> Invitation:
    """Resend: new token (the previous link stops working), back to pending,
    fresh validity window."""
    invitation.token = generate_token()
    invitation.status = Invitation.Status.PENDING
    invitation.expires_at = invitation_expiry()
    invitation.save(update_fields=["token", "status", "expires_at"])
    return invitation
