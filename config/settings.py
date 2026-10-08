"""
Django settings for the Smart belt Newborn Monitoring backend.

All secrets and environment-specific values come from environment variables
(see .env.example). Nothing sensitive is hardcoded. DEBUG defaults to False.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-only-key-do-not-use-in-prod")
DEBUG = env_bool("DJANGO_DEBUG", "false")
 

# DJANGO_ALLOWED_HOSTS is the documented name (.env.example, deployment guide);
# ALLOWED_HOSTS is still read for existing deployments.
_hosts_env = os.environ.get("DJANGO_ALLOWED_HOSTS") or os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _hosts_env.split(",") if h.strip()]

# optional: always allow localhost for local dev (10.0.2.2 = the host PC as
# seen from the Android emulator)
ALLOWED_HOSTS += ['localhost', '127.0.0.1', '10.0.2.2', 'centure-backend-3inq.onrender.com']
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "corsheaders",
    # Project apps (one per bounded context)
    "common",
    "users",
    "authentication",
    "babies",
    "belts",
    "measurements",
    "alerts",
    "notifications",
    "analysis",
    "invitations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.MedicalDataAuditMiddleware",  # audit log on sensitive endpoints
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: PostgreSQL in docker-compose / production, SQLite fallback for
# lightweight local test runs (pytest uses SQLite unless POSTGRES_HOST is set).
if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "belt"),
            "USER": os.environ.get("POSTGRES_USER", "belt"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.UserRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "user": os.environ.get("THROTTLE_USER", "1000/hour"),
        "auth": os.environ.get("THROTTLE_AUTH", "20/min"),        # login/register/refresh
        "ingest": os.environ.get("THROTTLE_INGEST", "600/min"),   # measurement ingest (bulk)
    },
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,  # revocation handled by authentication.Session
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Smart belt Newborn Monitoring API",
    "DESCRIPTION": (
        "REST API for the newborn vitals monitoring ecosystem. "
        "IMPORTANT: this system flags abnormal readings for caregiver or medical "
        "follow-up. It does NOT provide medical diagnoses."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = [
    o for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3100,http://localhost:8081"
    ).split(",") if o
]
# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
import sys

_IN_PYTEST = "pytest" in sys.modules or env_bool("CELERY_TASK_ALWAYS_EAGER", "false")
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
# In tests: run tasks inline and ignore results — no Redis required.
CELERY_RESULT_BACKEND = None if _IN_PYTEST else os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = _IN_PYTEST
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_IGNORE_RESULT = _IN_PYTEST
CELERY_BEAT_SCHEDULE = {
    # Detects belts that stopped sending data ("no_data" rule, Section 5).
    "detect-no-data": {
        "task": "analysis.tasks.detect_no_data",
        "schedule": float(os.environ.get("NO_DATA_CHECK_SECONDS", "60")),
    },
    # Marks pending parent invitations past their expiry as expired (enrollment refonte).
    "expire-invitations": {
        "task": "invitations.tasks.expire_invitations",
        "schedule": float(os.environ.get("INVITATION_EXPIRY_CHECK_SECONDS", "3600")),
    },
}

# ---------------------------------------------------------------------------
# FCM (Firebase Cloud Messaging, HTTP v1 API)
# ---------------------------------------------------------------------------
FCM_PROJECT_ID = os.environ.get("FCM_PROJECT_ID", "")
FCM_SERVICE_ACCOUNT_FILE = os.environ.get("FCM_SERVICE_ACCOUNT_FILE", "")

# ---------------------------------------------------------------------------
# Parent invitations (enrollment refonte): validity of an invitation link.
# ---------------------------------------------------------------------------
INVITATION_TTL_DAYS = int(os.environ.get("INVITATION_TTL_DAYS", "7"))

# ---------------------------------------------------------------------------
# Alert thresholds for the rule engine — the single source of truth (older
# child). Every key is env-overridable. The mobile app mirrors the defaults
# in lib/core/vital_thresholds.dart (live tile colours only);
# analysis/tests/test_classifier.py fails if the two drift apart.
# How each value is used: analysis/classifier.py.
# ---------------------------------------------------------------------------
def _threshold(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


# Key names deliberately differ from the old newborn keys (HR_LOW_BPM,
# RESP_LOW_BRPM, TEMP_HIGH_C, …) so a stale .env cannot override them.
ANALYSIS_THRESHOLDS = {
    # Heart rate (bpm)
    "HR_REST_HIGH_BPM": _threshold("HR_REST_HIGH_BPM", 100.0),      # > : warning at rest
    "HR_EFFORT_HIGH_BPM": _threshold("HR_EFFORT_HIGH_BPM", 160.0),  # > : warning any time
    "HR_CRITICAL_HIGH_BPM": _threshold("HR_CRITICAL_HIGH_BPM", 180.0),  # > sustained: critical
    "HR_WARN_LOW_BPM": _threshold("HR_WARN_LOW_BPM", 50.0),          # < : warning
    "HR_CRITICAL_LOW_BPM": _threshold("HR_CRITICAL_LOW_BPM", 40.0),  # < : critical
    # Respiratory rate (breaths/min)
    "RESP_REST_HIGH_BRPM": _threshold("RESP_REST_HIGH_BRPM", 30.0),      # > : warning at rest
    "RESP_EFFORT_HIGH_BRPM": _threshold("RESP_EFFORT_HIGH_BRPM", 40.0),  # > : critical at rest, warning after effort
    "RESP_CRITICAL_HIGH_BRPM": _threshold("RESP_CRITICAL_HIGH_BRPM", 50.0),  # > : critical any time
    "RESP_WARN_LOW_BRPM": _threshold("RESP_WARN_LOW_BRPM", 12.0),        # < : warning
    "RESP_CRITICAL_LOW_BRPM": _threshold("RESP_CRITICAL_LOW_BRPM", 8.0),  # < : critical
    # Temperature (°C)
    "TEMP_INFO_HIGH_C": _threshold("TEMP_INFO_HIGH_C", 37.5),          # > : info
    "TEMP_FEVER_C": _threshold("TEMP_FEVER_C", 38.0),                  # >= : warning
    "TEMP_CRITICAL_HIGH_C": _threshold("TEMP_CRITICAL_HIGH_C", 39.0),  # >= : critical
    "TEMP_WARN_LOW_C": _threshold("TEMP_WARN_LOW_C", 36.0),            # < : warning
    "TEMP_CRITICAL_LOW_C": _threshold("TEMP_CRITICAL_LOW_C", 35.0),    # < : critical
    # Battery (%)
    "BATTERY_INFO_PCT": _threshold("BATTERY_INFO_PCT", 20.0),          # < : info
    "BATTERY_WARN_PCT": _threshold("BATTERY_WARN_PCT", 10.0),          # < : warning
    # Persistence: consecutive out-of-range readings (5 s cadence) needed
    # before an alert fires, so one noisy sample never raises one.
    "PERSIST_READINGS": _threshold("PERSIST_READINGS", 3),
    "PERSIST_CRITICAL_READINGS": _threshold("PERSIST_CRITICAL_READINGS", 6),  # HR / respiration
    "PERSIST_WINDOW_S": _threshold("PERSIST_WINDOW_S", 300),  # streak readings must be this recent
    "NO_DATA_MINUTES": _threshold("NO_DATA_MINUTES", 5.0),
}

# Security hardening (effective behind nginx TLS termination — see deployment guide)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
    # Never log request bodies on auth endpoints (passwords). Enforced by not
    # adding any request-body logging middleware; audit middleware logs metadata only.
}
