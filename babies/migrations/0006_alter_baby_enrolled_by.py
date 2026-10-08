# Refonte Phase 1 (schema, step 3 of 3): enrolled_by becomes required once
# every existing row has been backfilled by 0005.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("babies", "0005_backfill_legacy_enrollment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="baby",
            name="enrolled_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="enrolled_babies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
