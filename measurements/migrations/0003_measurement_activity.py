# Activity context for the alert rules (analysis/classifier.py). Reversible:
# AddField — existing rows get "unknown".

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('measurements', '0002_respiration_replaces_spo2_movement'),
    ]

    operations = [
        migrations.AddField(
            model_name='measurement',
            name='activity',
            field=models.CharField(choices=[('sleep', 'Sleep'), ('rest', 'Rest'), ('effort', 'Effort'), ('recovery', 'Recovery'), ('unknown', 'Unknown')], default='unknown', max_length=10),
        ),
    ]
