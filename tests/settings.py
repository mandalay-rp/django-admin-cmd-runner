"""Минимальный Django-конфиг для запуска unit-тестов пакета.

Используется только в CI/pytest. Реальные проекты подключают
``command_runner`` в свой ``settings.py``.
"""

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "command_runner",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    },
}

STATIC_URL = "/static/"

ROOT_URLCONF = "tests.urls"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- command_runner ---
COMMAND_RUNNER_QUEUE = "rq"
COMMAND_RUNNER_RQ_REDIS_URL = "redis://localhost:6379/2"
COMMAND_RUNNER_RQ_QUEUE = "default"
COMMAND_RUNNER_COMMANDS = [
    {
        "name": "demo_long_command",
        "label": "Demo long command",
        "args_help": "--steps N",
    },
]
