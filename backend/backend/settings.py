"""
Django settings for MWW Translator Studio backend.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Vendored translation engine (comic_translator package)
ENGINE_DIR = BASE_DIR / "studio_engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

# Where Persian fonts live (scanned by /api/fonts)
FONTS_DIR = Path(os.environ.get("STUDIO_FONTS_DIR", BASE_DIR / "fonts"))

from django.core.exceptions import ImproperlyConfigured

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-7pa@xtfbg(0!*t-1m75=rr$dioc-0#woxxxmv=5#0qqdl-r%f3",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# Fail-closed: the insecure fallback key is only acceptable when DEBUG=1 was
# explicitly requested. Any other DJANGO_DEBUG value (including typos like
# "0 " or "true") must supply a real key, so a prod misconfiguration cannot
# silently ship DEBUG=True with a committed session-forgery secret.
if not DEBUG and SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set via environment when DJANGO_DEBUG is "
        "not exactly '1'"
    )

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",")

# The Next.js proxy normalizes trailing slashes; auto-appending would create
# redirect loops. All API consumers call exact slashed paths instead.
APPEND_SLASH = False

# ── Apps ────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local
    "studio",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# ── Database ────────────────────────────────────────────────────────────────

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ── Auth ────────────────────────────────────────────────────────────────────
# No login/signup/admin: the studio is a personal, unauthenticated app.
# django.contrib.auth stays installed only because the test client's
# force_login and the ORM anonymous-user plumbing assume it.


# ── i18n ────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static & Media ──────────────────────────────────────────────────────────

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Large PDF uploads
DATA_UPLOAD_MAX_MEMORY_SIZE = 512 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── DRF ─────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": None,
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# ── CORS / CSRF (frontend dev server) ───────────────────────────────────────

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ── Production hardening (applied when DEBUG is off) ────────────────────────

# Extra browser origins (LAN IP, domain) can be added without touching code:
#   FRONTEND_ORIGIN=https://studio.example.com,http://192.168.1.20:3000
_extra_origins = [
    o.strip() for o in os.environ.get("FRONTEND_ORIGIN", "").split(",")
    if o.strip()
]
CORS_ALLOWED_ORIGINS += _extra_origins
CSRF_TRUSTED_ORIGINS += _extra_origins

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

    # HTTPS enforcement is opt-in via DJANGO_HTTPS=1 so a plain-HTTP LAN
    # deployment still works: secure cookies over plain HTTP make the browser
    # drop the session, silently breaking login. When enabled, secure cookies,
    # HSTS and SSL redirect all activate.
    if os.environ.get("DJANGO_HTTPS", "0") == "1":
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_SSL_REDIRECT = True
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Sessions expire after 7 days of inactivity instead of 2 weeks.
SESSION_COOKIE_AGE = 7 * 24 * 60 * 60
