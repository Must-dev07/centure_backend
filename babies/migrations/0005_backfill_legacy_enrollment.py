# Refonte Phase 1 (data, step 2 of 3): backfill existing babies.
#
# Owner decisions / REFONTE_system.md §2.1:
# - every existing baby gets enrollment_reason="other" and the legacy note
#   below (no medical reason is inferred from existing data);
#   gestational_age_weeks stays empty;
# - enrolled_by = the first available Doctor/Admin user (active, lowest id),
#   or the first superuser if there is no other choice. If there are babies but
#   no such user at all, the migration stops with an explicit error instead of
#   inventing one.
# No enrollment medical-history entries are backfilled (only newly created
# babies get one). Reverse: no-op; 0004's reverse removes these columns.

from django.db import migrations

LEGACY_ENROLLMENT_REASON = "other"
LEGACY_ENROLLMENT_NOTES = "Legacy enrollment — original enrollment reason was not recorded."


def pick_legacy_enroller(User):
    staff = (
        User.objects.filter(role__in=["doctor", "admin"], is_active=True).order_by("id").first()
    )
    if staff is not None:
        return staff
    return User.objects.filter(is_superuser=True).order_by("id").first()


def backfill_legacy_babies(apps, schema_editor):
    Baby = apps.get_model("babies", "Baby")
    User = apps.get_model("users", "User")

    legacy = Baby.objects.all()
    if not legacy.exists():
        return

    enroller = pick_legacy_enroller(User)
    if enroller is None:
        raise RuntimeError(
            "Cannot backfill Baby.enrolled_by: no Doctor/Admin user and no superuser exists. "
            "Create a doctor, admin, or superuser account, then run the migration again."
        )

    legacy.update(
        enrollment_reason=LEGACY_ENROLLMENT_REASON,
        enrollment_notes=LEGACY_ENROLLMENT_NOTES,
        enrolled_by=enroller,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("babies", "0004_baby_enrollment_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_legacy_babies, migrations.RunPython.noop),
    ]
