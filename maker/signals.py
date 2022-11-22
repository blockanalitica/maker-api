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
        if instance.underlying_address == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2":
            Asset.objects.filter(
                address="0xae78736cd615f374d3085123a210448e74fc6393"
            ).update(price=instance.price, modified=datetime.now())

        Asset.objects.filter(address=instance.underlying_address).update(
            price=instance.price, modified=datetime.now()
        )
