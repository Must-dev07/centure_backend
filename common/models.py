from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Access log for sensitive (medical) data — Section 7 security checklist.

    Written by MedicalDataAuditMiddleware. Append-only by convention: no
    update/delete API is exposed for this table.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512)
    status_code = models.PositiveSmallIntegerField()
    ip_address = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.method} {self.path} -> {self.status_code}"
