"""Baby + append-only MedicalHistory entries + doctor assignment requests."""
from django.conf import settings
from django.db import models

from users.models import Doctor, Parent


class Baby(models.Model):
    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        UNSPECIFIED = "unspecified"

    name = models.CharField(max_length=100)
    birth_date = models.DateField()
    weight_grams = models.PositiveIntegerField(help_text="Birth/current weight in grams")
    gender = models.CharField(max_length=12, choices=Gender.choices, default=Gender.UNSPECIFIED)
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE, related_name="babies")
    assigned_doctor = models.ForeignKey(
        Doctor, null=True, blank=True, on_delete=models.SET_NULL, related_name="patients"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "babies"

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class MedicalHistoryEntry(models.Model):
    """Append-only medical history: entries are never edited or deleted via the
    API; corrections are made by appending a new entry referencing the old one."""

    baby = models.ForeignKey(Baby, on_delete=models.CASCADE, related_name="medical_history")
    title = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    recorded_by = models.ForeignKey(Doctor, null=True, on_delete=models.SET_NULL)
    supersedes = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "medical history entries"


class DoctorAssignmentRequest(models.Model):
    """Section 3 workflow: a parent requests a doctor for their baby; the
    doctor accepts or declines. Only on acceptance does `Baby.assigned_doctor`
    actually change — a pending request never touches it. Admins bypass this
    entirely and assign/remove doctors directly (BabyDetailView PATCH)."""

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        DECLINED = "declined"
        CANCELLED = "cancelled"

    baby = models.ForeignKey(Baby, on_delete=models.CASCADE, related_name="doctor_requests")
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="assignment_requests")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.baby} -> Dr {self.doctor_id} [{self.status}]"
