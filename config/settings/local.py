# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from config.settings.base import *  # noqa
from config.settings.base import INSTALLED_APPS, MIDDLEWARE

CORS_ALLOW_ALL_ORIGINS = True

INSTALLED_APPS += [
    "debug_toolbar",
]

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE

SHELL_PLUS_IMPORTS = []

SHELL_PLUS_PRINT_SQL = False


def show_toolbar(request):
    return True


DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": show_toolbar,
}

CELERY_TASK_ALWAYS_EAGER = True

CACHE_MIDDLEWARE_SECONDS = 0
CORS_ALLOW_ALL_ORIGINS = True
