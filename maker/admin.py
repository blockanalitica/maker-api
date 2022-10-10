# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.contrib import admin

from .models import ForumPost


@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = [
        "segments",
        "title",
        "publish_date",
        "publisher",
        "created",
    ]
