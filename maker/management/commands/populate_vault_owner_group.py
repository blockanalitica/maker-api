# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.core.management.base import BaseCommand

from maker.models import VaultOwner, VaultOwnerGroup


class Command(BaseCommand):
    def handle(self, *args, **options):
        whales = VaultOwner.objects.filter(tags__contains=["whale"])
        for whale in whales:
            group, _ = VaultOwnerGroup.objects.get_or_create(
                name=whale.name,
                defaults={
                    "tags": ["whale"],
                },
            )
            whale.group = group
            whale.tags.remove("whale")
            whale.save()

        self.stdout.write("Done")
