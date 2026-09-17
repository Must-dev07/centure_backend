from django.contrib import admin

from .models import Bracelet, Pairing


class PairingInline(admin.TabularInline):
    model = Pairing
    extra = 0
    readonly_fields = ["paired_at"]


@admin.register(Bracelet)
class BraceletAdmin(admin.ModelAdmin):
    list_display = ["serial_number", "baby", "status", "battery_level", "last_seen_at", "firmware_version"]
    list_filter = ["status"]
    search_fields = ["serial_number"]
    inlines = [PairingInline]
