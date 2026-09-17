from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "method", "path", "status_code", "ip_address"]
    list_filter = ["method", "status_code"]
    date_hierarchy = "created_at"
    # Append-only: nothing is editable or deletable from the admin.
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
