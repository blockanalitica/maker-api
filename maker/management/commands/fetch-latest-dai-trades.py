# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from maker.models import DAITrade
from maker.modules.dai_trades import DAITradesFetcher
from maker.utils.utils import get_date_timestamp_days_ago


class Command(BaseCommand):
    """Script for fetching latest DAI trades.
    Fetches only last ~3 days of data.
    This script should only be used in development!
    """

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise Exception("This script should not be used in production!")

        start = datetime.now()

        last_trade = DAITrade.objects.all().order_by("-timestamp").first()

        days_ago = get_date_timestamp_days_ago(3)
        if not last_trade or last_trade.timestamp < days_ago:
            # Create a dummy DAITrade so that the DAITradesFetcher goes on from there
            DAITrade.objects.create(
                timestamp=days_ago,
                datetime=datetime.fromtimestamp(days_ago),
                pair="DAI-USD",
                exchange="dummy",
                amount=Decimal("0"),
                price=Decimal("0"),
                dai_price=Decimal("0"),
                dai_amount=Decimal("0"),
            )

        fetcher = DAITradesFetcher()
        fetcher.fetch(days=30)

        self.stdout.write("Done: {}".format(datetime.now() - start))
