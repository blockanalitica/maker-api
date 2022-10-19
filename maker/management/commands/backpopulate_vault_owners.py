# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.core.management.base import BaseCommand

from maker.models import MakerWallet, VaultOwner


class Command(BaseCommand):
    def handle(self, *args, **options):
        VaultOwner.objects.update(name=None, tags=[])
        for wallet in MakerWallet.objects.select_related("owner").all():
            try:
                owner = VaultOwner.objects.get(address__iexact=wallet.address)
            except VaultOwner.DoesNotExist:
                self.stderr.write(
                    "Can't find owner with address {}".format(wallet.address)
                )
                continue

            owner.name = wallet.owner.name
            try:
                owner.tags.remove("institution")
            except ValueError:
                pass
            if wallet.is_institution:
                owner.tags.append("institution")

            try:
                owner.tags.remove("whale")
            except ValueError:
                pass
            if wallet.owner.is_whale:
                owner.tags.append("whale")

            owner.save()
