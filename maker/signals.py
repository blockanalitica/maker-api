# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

from django.db.models.signals import post_save
from django.dispatch import receiver

from maker.models import Asset


@receiver(post_save, sender="maker.TokenPriceHistory")
def chainlink_price_change(sender, instance, created, **kwards):
    if instance.price > 0:
        Asset.objects.filter(address=instance.underlying_address).update(
            price=instance.price, modified=datetime.now()
        )
