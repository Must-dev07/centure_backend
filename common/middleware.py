"""Audit middleware: logs metadata (never bodies) of accesses to sensitive
medical endpoints. Passwords / payloads are intentionally NOT recorded."""
import logging

logger = logging.getLogger("audit")

# Path prefixes considered medically sensitive.
SENSITIVE_PREFIXES = (
    "/api/v1/babies",
    "/api/v1/measurements",
    "/api/v1/alerts",
)


class MedicalDataAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(SENSITIVE_PREFIXES):
            try:
                from common.models import AuditLog

                user = getattr(request, "user", None)
                AuditLog.objects.create(
                    user=user if getattr(user, "is_authenticated", False) else None,
                    method=request.method,
                    path=request.path[:512],
                    status_code=response.status_code,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
            except Exception:  # audit must never break the request path
                logger.exception("audit log write failed")
        return response
