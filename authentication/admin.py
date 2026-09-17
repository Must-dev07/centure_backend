from django.contrib import admin

from .models import Session


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ["user", "refresh_jti", "created_at", "expires_at", "revoked_at", "ip_address"]
    list_filter = ["revoked_at"]
    readonly_fields = [f.name for f in Session._meta.fields]

    def has_add_permission(self, request):
        return False
