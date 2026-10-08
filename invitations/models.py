"""Parent invitations: a baby enrolled for an email with no parent account yet
gets a pending Invitation; the parent accepts it with the token (link) and
their account is created or linked."""
from django.conf import settings
from django.db import models

from babies.models import Baby


class Invitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        EXPIRED = "expired"

    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    token = models.CharField(max_length=64, unique=True, db_index=True)  # secrets.token_urlsafe
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invitations_sent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    babies = models.ManyToManyField(Baby, related_name="pending_invitations", blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"Invitation {self.email} [{self.status}]"
