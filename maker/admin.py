# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.contrib import admin

from .models import ForumPost, VaultOwner


@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = [
        "segments",
        "title",
        "publish_date",
        "publisher",
        "created",
    ]


@admin.register(VaultOwner)
class VaultOwnerAdmin(admin.ModelAdmin):
    search_fields = ["address", "ens", "name"]
    readonly_fields = (
        "address",
        "ens",
    )
    list_display = [
        "address",
        "name",
        "ens",
        "tags",
        "created",
    ]
