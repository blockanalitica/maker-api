# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.apps import AppConfig


class MakerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "maker"

    def ready(self):
        import maker.signals  # noqa
