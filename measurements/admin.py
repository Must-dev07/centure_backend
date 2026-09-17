from django.contrib import admin

from .models import Measurement


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = ["baby", "bracelet", "heart_rate", "temperature", "spo2", "battery", "recorded_at"]
    list_filter = ["skin_contact"]
    date_hierarchy = "recorded_at"
    # Read-only in admin — measurements come from devices, never hand-edited.
    readonly_fields = [f.name for f in Measurement._meta.fields]

    def has_add_permission(self, request):
        return False
