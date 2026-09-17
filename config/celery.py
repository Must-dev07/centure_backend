"""Celery application — used by celery-worker and celery-beat containers."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("bracelet_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
