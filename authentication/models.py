"""Session model: tracks refresh tokens (by JTI) so they can be rotated and
revoked server-side. On refresh, the old session row is revoked and a new one
created; on logout, the session is revoked immediately."""
from django.conf import settings
from django.db import models


class Session(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    refresh_jti = models.CharField(max_length=64, unique=True, db_index=True)
    user_agent = models.CharField(max_length=256, blank=True)
    ip_address = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __str__(self) -> str:  # pragma: no cover
        return f"Session {self.refresh_jti[:8]}… for {self.user_id}"
