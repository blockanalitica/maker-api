# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

import environ
import sentry_sdk
from corsheaders.defaults import default_headers
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

env = environ.Env()
environ.Env.read_env(env_file=".env")

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env("MAKER_SECRET_KEY", default="django-insecure-bzupfio1t9h")

DEBUG = env.bool("MAKER_DEBUG", default=False)

ALLOWED_HOSTS = [
    host
    for host in env("MAKER_ALLOWED_HOSTS", default="localhost;0.0.0.0;127.0.0.1").split(
        ";"
    )
    if host
]

INTERNAL_IPS = [ip for ip in env("MAKER_INTERNAL_IPS", default="").split(";") if ip]

CORS_ALLOWED_ORIGINS = [
    cors for cors in env("MAKER_CORS_ALLOWED_ORIGINS", default="").split(";") if cors
]
CORS_ALLOW_HEADERS = list(default_headers) + [
    "sentry-trace",
]

CSRF_TRUSTED_ORIGINS = ["https://*.blockanalitica.com"]

# Application definition

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "rest_framework",
    "corsheaders",
    "django_celery_beat",
    "maker.apps.MakerConfig",
]

MIDDLEWARE = [
    "maker.middleware.HealthCheckMiddleware",
    "django.middleware.cache.UpdateCacheMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.cache.FetchFromCacheMiddleware",
]

ROOT_URLCONF = "config.urls"

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
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql_psycopg2",
        "NAME": env("MAKER_DB_NAME", default="maker"),
        "USER": env("MAKER_DB_USER", default=""),
        "PASSWORD": env("MAKER_DB_PASSWORD", default=""),
        "HOST": env("MAKER_DB_HOST", default=""),
        "PORT": env("MAKER_DB_PORT", default="5432"),
    }
}


# Celery configuration options
CELERY_BROKER_URL = "redis://{}:{}/{}".format(
    env("MAKER_CELERY_REDIS_HOST", default=None),
    env("MAKER_CELERY_REDIS_PORT", default="6379"),
    env("MAKER_CELERY_REDIS_DB", default="3"),
)
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 45 * 60
CELERY_ALWAYS_EAGER = False
CELERY_WORKER_MAX_TASKS_PER_CHILD = env.int(
    "CELERY_WORKER_MAX_TASKS_PER_CHILD", default=1000
)
CELERY_WORKER_PREFETCH_MULTIPLIER = env.int(
    "CELERY_WORKER_PREFETCH_MULTIPLIER", default=1
)
CELERY_WORKER_MAX_MEMORY_PER_CHILD = env.int(
    "CELERY_WORKER_MAX_MEMORY_PER_CHILD", default=256000  # 256MB
)


CELERY_IMPORTS = [
    "maker.tasks",
]

# django-celery-beat configuration options
DJANGO_CELERY_BEAT_TZ_AWARE = False

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://{}:{}/{}".format(
            env("MAKER_REDIS_HOST", default=None),
            env("MAKER_REDIS_PORT", default="6379"),
            env("MAKER_REDIS_DB", default="3"),
        ),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "PARSER_CLASS": "redis.connection.HiredisParser",
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_CONNECT_TIMEOUT": 1,
            "SOCKET_TIMEOUT": 1,
        },
    }
}
CACHE_MIDDLEWARE_SECONDS = env.int("CACHE_MIDDLEWARE_SECONDS", default=10)
CACHE_MIDDLEWARE_KEY_PREFIX = env("CACHE_MIDDLEWARE_KEY_PREFIX", default="maker_api")

DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = env.bool(
    "DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS", default=True
)


# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = False

USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/
STATIC_URL = "static/"
STATICFILES_DIRS = []
STATIC_ROOT = BASE_DIR / "static"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

sentry_sdk.init(
    integrations=[DjangoIntegration()],
    send_default_pii=True,
    environment=env("MAKER_ENVIRONMENT", default=None),
    traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", default=0.0)),
)
ignore_logger("django.security.DisallowedHost")


STATSD_HOST = env("STATSD_HOST", default="localhost")
STATSD_PORT = env("STATSD_PORT", default=8125)
STATSD_PREFIX = env("STATSD_PREFIX", default=None)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": (
                "[%(asctime)s] %(name)s {%(module)s:%(lineno)d} PID=%(process)d "
                "%(levelname)s - %(message)s"
            )
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
        },
    },
    "loggers": {
        "django": {
            "propagate": True,
            "level": "INFO",
        },
        "django_bulk_load": {
            "propagate": True,
            "level": "WARNING",
        },
        "maker": {
            "propagate": True,
            "level": env("MAKER_LOG_LEVEL", default="INFO"),
        },
        "": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}


ETH_NODE = env("ETH_NODE", default="")
ETH_NODE_MAKER = env("ETH_NODE_MAKER", default="")

MCDSTATE_SNOWFLAKE_PASSWORD = env("MCDSTATE_SNOWFLAKE_PASSWORD", default="")
MCDSTATE_SNOWFLAKE_ACCOUNT = env("MCDSTATE_SNOWFLAKE_ACCOUNT", default="")
MCDSTATE_SNOWFLAKE_USER = env("MCDSTATE_SNOWFLAKE_USER", default="")
MCDSTATE_SNOWFLAKE_ROLE = env("MCDSTATE_SNOWFLAKE_ROLE", default="")
MCDSTATE_SNOWFLAKE_WAREHOUSE = env("MCDSTATE_SNOWFLAKE_WAREHOUSE", default="")
MCDSTATE_SNOWFLAKE_DATABASE = env("MCDSTATE_SNOWFLAKE_DATABASE", default="")
MCDSTATE_SNOWFLAKE_SCHEMA = env("MCDSTATE_SNOWFLAKE_SCHEMA", default="")
MCDSTATE_SNOWFLAKE_EXECUTE_TIMEOUT = int(
    env("MCDSTATE_SNOWFLAKE_EXECUTE_TIMEOUT", default=60)
)

MCDSTATE_API_CLIENT_ID = env("MCDSTATE_API_CLIENT_ID", default="")
MCDSTATE_API_USERNAME = env("MCDSTATE_API_USERNAME", default="")
MCDSTATE_API_PASSWORD = env("MCDSTATE_API_PASSWORD", default="")

MAKER_S3_FILE_STORAGE_BUCKET = env("MAKER_S3_FILE_STORAGE_BUCKET", default="")
MAKER_AWS_S3_ACCESS_KEY_ID = env("MAKER_AWS_S3_ACCESS_KEY_ID", default="")
MAKER_AWS_S3_SECRET_ACCESS_KEY = env("MAKER_AWS_S3_SECRET_ACCESS_KEY", default="")

BLOCKNATIVE_API_KEY = env("BLOCKNATIVE_API_KEY", default="")

DISCORD_ALERT_BOT_WEBHOOK_BA = env("DISCORD_ALERT_BOT_WEBHOOK_BA", default="")
DISCORD_ALERT_BOT_WEBHOOK_MKR = env("DISCORD_ALERT_BOT_WEBHOOK_MKR", default="")

CRYPTOCOMPARE_API_KEY = env("CRYPTOCOMPARE_API_KEY", default="")

BLOCKANALITICA_PAPI_URL = env("BLOCKANALITICA_PAPI_URL", default="")
BLOCKANALITICA_DATALAKE_URL = env("BLOCKANALITICA_DATALAKE_URL", default="")
