import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "insecure-dev-only-key-do-not-use-in-prod",
)

DEBUG = env_bool("DJANGO_DEBUG", "false")


ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

# Local development
ALLOWED_HOSTS += ["localhost", "127.0.0.1"]

# Render
if not DEBUG:
    ALLOWED_HOSTS.append("centure-backend-3inq.onrender.com")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# PostgreSQL is used both locally and in production.
#
# Local .env:
# DATABASE_URL=postgresql://cent_admin:password@localhost:5432/centure
#
# Render Environment:
# DATABASE_URL=<Render Internal Database URL>

DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=60,
    )
}
