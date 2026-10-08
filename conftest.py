"""Shared pytest fixtures: force SQLite + eager Celery in tests, factories,
authenticated API clients per role."""
import os

# Tests always run on SQLite with eager (in-process) Celery — no external services.
os.environ.pop("POSTGRES_HOST", None)
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

import pytest
from rest_framework.test import APIClient

from tests.factories import (
    AdminFactory,
    BabyFactory,
    beltFactory,
    DoctorFactory,
    ParentFactory,
)


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    # DRF throttle counters live in the cache; without a reset, the shared
    # anonymous "auth" budget (login, register, invitation accept) leaks
    # between tests and later tests get 429s.
    from django.core.cache import cache

    cache.clear()
    yield


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def parent():
    return ParentFactory()


@pytest.fixture
def doctor():
    return DoctorFactory()


@pytest.fixture
def admin_user():
    return AdminFactory()


@pytest.fixture
def baby(parent, doctor):
    return BabyFactory(parent=parent, assigned_doctor=doctor)


@pytest.fixture
def belt(baby):
    b = beltFactory()
    b.pair_with(baby)
    b.refresh_from_db()
    return b


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def parent_client(parent):
    return _client_for(parent.user)


@pytest.fixture
def doctor_client(doctor):
    return _client_for(doctor.user)


@pytest.fixture
def admin_client(admin_user):
    return _client_for(admin_user)
