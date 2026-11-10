"""Django settings. Everything that differs per installation comes from DEPOTBUCH_*
environment variables; the defaults suit a local run, not the homelab deployment.
"""

import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# One database (and later its data files) per installation.
DATA_DIR = Path(os.environ.get("DEPOTBUCH_DATA_DIR", Path.cwd())).resolve()

# A deployment must set DEPOTBUCH_SECRET_KEY. Without it a random key is generated per
# process, which is safe but logs everyone out on every restart.
SECRET_KEY = os.environ.get("DEPOTBUCH_SECRET_KEY") or get_random_secret_key()
DEBUG = _env_bool("DEPOTBUCH_DEBUG")
ALLOWED_HOSTS = _env_list("DEPOTBUCH_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "depotbuch.web.portfolio",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "depotbuch.web.urls"
WSGI_APPLICATION = "depotbuch.web.wsgi.application"

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

# SQLite by default; PostgreSQL support lands with the deployment milestone.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "depotbuch.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = DATA_DIR / "static"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
