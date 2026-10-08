# Refonte Phase 1 (schema, step 1 of 3): enrollment fields on Baby.
#
# - `parent` becomes nullable with on_delete=SET_NULL (a baby may exist before
#   its parent account). Reversing this step fails if babies without a parent
#   exist at that point; no data is ever deleted to make a reverse succeed.
# - `enrolled_by` is added as nullable here; 0005 backfills it and 0006 makes it
#   required, so existing rows are never left invalid.
# - `enrollment_reason` gets a one-off database default ("other") only to fill
#   existing rows; 0005 sets the legacy note. The model itself has no default.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("babies", "0003_doctorassignmentrequest"),
        ("users", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="baby",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="babies",
                to="users.parent",
            ),
        ),
        migrations.AddField(
            model_name="baby",
            name="enrollment_reason",
            field=models.CharField(
                choices=[
                    ("prematurity", "Prematurity"),
                    ("clinical_sign", "Clinical Sign"),
                    ("congenital_condition", "Congenital Condition"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=32,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="baby",
            name="enrollment_notes",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="baby",
            name="gestational_age_weeks",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="baby",
            name="enrolled_by",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="enrolled_babies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
