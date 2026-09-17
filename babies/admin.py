from django.contrib import admin

from .models import Baby, MedicalHistoryEntry


class MedicalHistoryInline(admin.TabularInline):
    model = MedicalHistoryEntry
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(Baby)
class BabyAdmin(admin.ModelAdmin):
    list_display = ["name", "birth_date", "gender", "parent", "assigned_doctor"]
    list_filter = ["gender"]
    search_fields = ["name", "parent__user__email"]
    inlines = [MedicalHistoryInline]
