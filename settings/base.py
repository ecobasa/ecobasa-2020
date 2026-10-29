"""
Base settings to build other settings files upon.
"""

from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

# ROOT_DIR = environ.Path(__file__) - 2
ROOT_DIR = Path(__file__).resolve(strict=True).parent.parent
APPS_DIR = ROOT_DIR

env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(ROOT_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = env.bool("DJANGO_DEBUG", False)
SITE_ID = env("DJANGO_SITE_ID", default=1)

# I18N
# ------------------------------------------------------------------------------
TIME_ZONE = "Europe/Berlin"
LANGUAGE_CODE = "en"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("de", _("German")),
    ("en", _("English")),
    ("es", _("Spanish")),
    ("fr", _("French")),
]

LOCALE_PATHS = [str(ROOT_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgis://ecobasa:ecobasa@localhost/ecobasa"
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# URLS
# ------------------------------------------------------------------------------
ROOT_URLCONF = "urls"
WSGI_APPLICATION = "wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.gis",
    "django.forms"
]

THIRD_PARTY_APPS = [
    "django_filters",
    "crispy_forms",
    "embed_video",
    "taggit",
    "croppie",
    "postman",
    "django_countries",
]

LOCAL_APPS = [
    "users",
    "homepage",
    "gift_economy.gifts",
    "communities",
    "notifications",
    "gift_economy.matches",
    "gift_economy.references",
    "projects",
]

# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Use BigAutoField by default to avoid implicit primary key warnings on Django 4+
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# MIGRATIONS
# ------------------------------------------------------------------------------
# MIGRATION_MODULES = {}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "homepage:homepage"
LOGOUT_REDIRECT_URL = "homepage:homepage"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "users:login"
# https://docs.djangoproject.com/en/dev/ref/settings/#session-expire-at-browser-close
# SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# PASSWORDS
# ------------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.BCryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        ),
        "OPTIONS": {"user_attributes": ("username", "name", "email")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "users.middleware.UserLanguageMiddleware",
    "users.middleware.LastSeenMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static"), str(ROOT_DIR / "node_modules")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]


# MEDIA
# ------------------------------------------------------------------------------
MEDIA_ROOT = str(APPS_DIR / "media")
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [APPS_DIR / "templates"],
        "OPTIONS": {
            "debug": DEBUG,
            "libraries": {
                    "my_crispy_helpers": "templatetags.my_crispy_helpers",
                    "site_tags": "templatetags.site_tags",
                },
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.unread_notifications",
                "gift_economy.references.context_processors.pending_reference_skills",
                "gift_economy.matches.context_processors.new_suggestions",
                "gift_economy.matches.context_processors.lending_calendar",
            ],
        },
    }
]

# https://docs.djangoproject.com/en/dev/ref/forms/renderers/#templatessetting
# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"


# FIXTURES
# ------------------------------------------------------------------------------
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)


# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-browser-xss-filter
SECURE_BROWSER_XSS_FILTER = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"


# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
# ADMIN_URL = r"^admin/"
# ADMINS = [("Name", "admin@example.com")]
# MANAGERS = ADMINS

# CRISPY FORMS
# ------------------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "crispy_template_pack"
CRISPY_TEMPLATE_PACK = "crispy_template_pack"

# POSTMAN SETTINGS
# ------------------------------------------------------------------------------
POSTMAN_AUTO_MODERATE_AS = True
POSTMAN_DISALLOW_ANONYMOUS = True
# Recipients are looked up by id: names aren't unique, and username is only set on legacy accounts.
POSTMAN_NAME_USER_AS = 'id'
POSTMAN_SHOW_USER_AS = 'name'

# MAP SETTINGS
# ------------------------------------------------------------------------------
STADIA_MAPS_KEY = env('STADIA_MAPS_KEY', default='cb8069a3-9585-4989-a6a8-572b5c3f4ffb')

# APP SETTINGS
# ------------------------------------------------------------------------------
# Absolute links in emails sent outside a request (management commands)
SITE_URL = env("DJANGO_SITE_URL", default="https://ecobasa.org")

# REFERENCE REQUESTS
# ------------------------------------------------------------------------------
# After a match, both sides are asked for their story (send_reference_requests, daily, see crontab).
# Days after the stay ended or the agreed date, or after acceptance if there was no date:
REFERENCE_REQUEST_DELAY_DAYS = env.int("REFERENCE_REQUEST_DELAY_DAYS", default=1)
REFERENCE_REQUEST_UNDATED_DELAY_DAYS = env.int("REFERENCE_REQUEST_UNDATED_DELAY_DAYS", default=7)
# Matches that were due longer ago than this are never asked about (e.g. on first rollout)
REFERENCE_REQUEST_MAX_AGE_DAYS = env.int("REFERENCE_REQUEST_MAX_AGE_DAYS", default=30)
# Replies by email: answers to stories+<key>@… are read from this IMAP mailbox
# (fetch_reference_replies, every few minutes, see crontab). Without an address, emails only offer the link.
REFERENCE_REPLY_ADDRESS = env("REFERENCE_REPLY_ADDRESS", default="")
REFERENCE_IMAP_HOST = env("REFERENCE_IMAP_HOST", default="")
REFERENCE_IMAP_USER = env("REFERENCE_IMAP_USER", default="")
REFERENCE_IMAP_PASSWORD = env("REFERENCE_IMAP_PASSWORD", default="")
REFERENCE_IMAP_FOLDER = env("REFERENCE_IMAP_FOLDER", default="INBOX")
# Development: read replies from Mailpit's API instead of IMAP
REFERENCE_MAILPIT_URL = env("REFERENCE_MAILPIT_URL", default="")

# PROJECTS
# ------------------------------------------------------------------------------
# A project nobody updated or confirmed for this many days is stale: its ambassador is
# asked whether it is still current (archive_stale_projects, daily, see crontab) ...
PROJECT_STALE_DAYS = env.int("PROJECT_STALE_DAYS", default=60)
# ... and it is archived if nobody confirms it within this many days. Dated projects are
# archived the day after they end.
PROJECT_ARCHIVE_GRACE_DAYS = env.int("PROJECT_ARCHIVE_GRACE_DAYS", default=14)
