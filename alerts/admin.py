from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["type", "severity", "baby", "value", "triggered_at", "resolved_at", "acknowledged_by"]
    list_filter = ["type", "severity"]
    date_hierarchy = "triggered_at"
    search_fields = ["baby__name"]
