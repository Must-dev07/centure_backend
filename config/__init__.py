"""Ensure the Celery app is loaded whenever Django starts, so @shared_task
binds to it (and honours CELERY_* settings such as task_always_eager)."""
from .celery import app as celery_app

__all__ = ("celery_app",)
