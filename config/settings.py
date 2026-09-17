"""
Django settings for the Smart Bracelet Newborn Monitoring backend.

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
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

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
    "bracelets",
    "measurements",
    "alerts",
    "notifications",
    "analysis",
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
            "NAME": os.environ.get("POSTGRES_DB", "bracelet"),
            "USER": os.environ.get("POSTGRES_USER", "bracelet"),
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
    "TITLE": "Smart Bracelet Newborn Monitoring API",
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
    # Detects bracelets that stopped sending data ("no_data" rule, Section 5).
    "detect-no-data": {
        "task": "analysis.tasks.detect_no_data",
        "schedule": float(os.environ.get("NO_DATA_CHECK_SECONDS", "60")),
    },
}

# ---------------------------------------------------------------------------
# FCM (Firebase Cloud Messaging, HTTP v1 API)
# ---------------------------------------------------------------------------
FCM_PROJECT_ID = os.environ.get("FCM_PROJECT_ID", "")
FCM_SERVICE_ACCOUNT_FILE = os.environ.get("FCM_SERVICE_ACCOUNT_FILE", "")

# ---------------------------------------------------------------------------
# Alert thresholds for the rule engine (env-overridable, sensible newborn defaults)
# ---------------------------------------------------------------------------
ANALYSIS_THRESHOLDS = {
    "TEMP_HIGH_C": float(os.environ.get("TEMP_HIGH_C", "38.0")),
    "TEMP_LOW_C": float(os.environ.get("TEMP_LOW_C", "36.0")),
    "SPO2_LOW_PCT": float(os.environ.get("SPO2_LOW_PCT", "92.0")),
    "HR_HIGH_BPM": float(os.environ.get("HR_HIGH_BPM", "180.0")),
    "HR_LOW_BPM": float(os.environ.get("HR_LOW_BPM", "90.0")),
    "BATTERY_LOW_PCT": float(os.environ.get("BATTERY_LOW_PCT", "15.0")),
    "NO_MOVEMENT_MINUTES": float(os.environ.get("NO_MOVEMENT_MINUTES", "20.0")),
    "NO_DATA_MINUTES": float(os.environ.get("NO_DATA_MINUTES", "5.0")),
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
