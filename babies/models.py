"""Baby + append-only MedicalHistory entries + doctor assignment requests."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from users.models import Doctor, Parent

ENROLLMENT_HISTORY_TITLE = "Enrôlement"


class Baby(models.Model):
    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        UNSPECIFIED = "unspecified"

    class EnrollmentReason(models.TextChoices):
        PREMATURITY = "prematurity"
        CLINICAL_SIGN = "clinical_sign"
        CONGENITAL_CONDITION = "congenital_condition"
        OTHER = "other"

    name = models.CharField(max_length=100)
    birth_date = models.DateField()
    weight_grams = models.PositiveIntegerField(help_text="Birth/current weight in grams")
    # Current length/height, kept up to date by the assigned doctor (optional:
    # babies enrolled before this field existed have none).
    height_cm = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, help_text="Current height in cm"
    )
    gender = models.CharField(max_length=12, choices=Gender.choices, default=Gender.UNSPECIFIED)
    # Nullable: a baby can be enrolled before its parent account exists
    # (the parent is linked when they accept their invitation).
    parent = models.ForeignKey(
        Parent, null=True, blank=True, on_delete=models.SET_NULL, related_name="babies"
    )
    assigned_doctor = models.ForeignKey(
        Doctor, null=True, blank=True, on_delete=models.SET_NULL, related_name="patients"
    )
    enrollment_reason = models.CharField(max_length=32, choices=EnrollmentReason.choices)
    enrollment_notes = models.TextField(blank=True)  # free-text detail of the observed clinical sign
    gestational_age_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    # Audit: which doctor/admin created the record.
    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="enrolled_babies"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "babies"

    def __str__(self) -> str:  # pragma: no cover
        return self.name

    def clean(self):
        super().clean()
        if self.enrollment_reason == self.EnrollmentReason.OTHER and not (self.enrollment_notes or "").strip():
            raise ValidationError(
                {"enrollment_notes": "A description is required when the enrollment reason is 'other'."}
            )

    def save(self, *args, **kwargs):
        creating = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creating:
                self._record_enrollment_entry()

    def _record_enrollment_entry(self):
        """First medical-history entry of every newly created baby. `recorded_by`
        is the enrolling doctor's profile; an admin enrollment has no Doctor, so
        it stays empty (Baby.enrolled_by remains the authoritative audit field)."""
        enrolled_by = self.enrolled_by
        doctor = (
            getattr(enrolled_by, "doctor_profile", None)
            if enrolled_by.role == "doctor"
            else None
        )
        MedicalHistoryEntry.objects.create(
            baby=self,
            title=ENROLLMENT_HISTORY_TITLE,
            details=self.enrollment_notes,
            recorded_by=doctor,
        )


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
