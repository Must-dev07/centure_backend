"""Celery tasks for the invitations app."""
from celery import shared_task
from django.utils import timezone


@shared_task
def expire_invitations() -> int:
    """Celery-beat watchdog (same mechanism as analysis.tasks.detect_no_data):
    pending invitations past their expiry become `expired`. Expired invitations
    can be renewed with the resend endpoint. Nothing is deleted."""
    from .models import Invitation

    return Invitation.objects.filter(
        status=Invitation.Status.PENDING, expires_at__lte=timezone.now()
    ).update(status=Invitation.Status.EXPIRED)
