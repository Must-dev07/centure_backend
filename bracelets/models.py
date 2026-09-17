"""Bracelet device registry + full Pairing history."""
from django.db import models
from django.utils import timezone

from babies.models import Baby


class Bracelet(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        INACTIVE = "inactive"
        MAINTENANCE = "maintenance"

    serial_number = models.CharField(max_length=64, unique=True, db_index=True)
    nickname = models.CharField(max_length=64, blank=True, help_text="Friendly display name, e.g. 'Emma's bracelet'")
    firmware_version = models.CharField(max_length=32, blank=True)
    baby = models.ForeignKey(  # current assignment; history lives in Pairing
        Baby, null=True, blank=True, on_delete=models.SET_NULL, related_name="bracelets"
    )
    battery_level = models.FloatField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.nickname or self.serial_number

    def pair_with(self, baby: Baby) -> "Pairing":
        """Atomically close any open pairing and open a new one. A baby has
        exactly one *active* bracelet: pairing a new one to a baby that
        already has one implements "replace bracelet" by auto-unpairing the
        old one (its own Pairing history is preserved, just closed)."""
        now = timezone.now()
        Pairing.objects.filter(bracelet=self, unpaired_at__isnull=True).update(unpaired_at=now)
        replaced = Bracelet.objects.filter(baby=baby).exclude(pk=self.pk)
        if replaced.exists():
            Pairing.objects.filter(bracelet__in=replaced, baby=baby, unpaired_at__isnull=True).update(
                unpaired_at=now
            )
            replaced.update(baby=None, status=Bracelet.Status.INACTIVE)
        self.baby = baby
        self.status = self.Status.ACTIVE
        self.save(update_fields=["baby", "status"])
        return Pairing.objects.create(bracelet=self, baby=baby)

    def unpair(self) -> None:
        Pairing.objects.filter(bracelet=self, unpaired_at__isnull=True).update(
            unpaired_at=timezone.now()
        )
        self.baby = None
        self.status = self.Status.INACTIVE
        self.save(update_fields=["baby", "status"])


class Pairing(models.Model):
    """Full pairing history — one row per pair/unpair cycle."""

    bracelet = models.ForeignKey(Bracelet, on_delete=models.CASCADE, related_name="pairings")
    baby = models.ForeignKey(Baby, on_delete=models.CASCADE, related_name="pairings")
    paired_at = models.DateTimeField(auto_now_add=True)
    unpaired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-paired_at"]
