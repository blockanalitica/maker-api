# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import random
import string
from datetime import datetime
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from maker import constants


def _random_string(length):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


class DAITradeFactory(DjangoModelFactory):
    timestamp = Decimal("1631191736.563")
    datetime = datetime(2021, 9, 9, 12, 48, 56, 563000)
    pair = "DAI-USD"
    exchange = "coinbase"
    amount = Decimal("43.28412")
    price = Decimal("1.000053")

    class Meta:
        model = "maker.DAITrade"


class ForumPostFactory(DjangoModelFactory):
    segments = ["My Segment"]
    vault_types = []
    title = factory.Sequence(lambda n: f"Forum Post {n}")
    description = factory.Sequence(lambda n: f"Forum Post Description {n}")
    url = "https://maker.blockanalitica.com/"
    publish_date = factory.LazyFunction(datetime.now)
    publisher = "spongebob"

    class Meta:
        model = "maker.ForumPost"


class AssetFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Asset{n}")
    symbol = factory.Sequence(lambda n: f"ASSET{n}")
    underlying_symbol = factory.Sequence(lambda n: f"ASSET{n}")
    type = constants.ASSET_TYPE_TOKEN
    address = factory.LazyAttribute(
        lambda obj: "0x{}{}".format(
            obj.symbol.lower(), _random_string(40 - len(obj.symbol))
        )
    )
    decimals = 18
    price = Decimal("41000.53")

    class Meta:
        model = "maker.Asset"


class SlippagePairFactory(DjangoModelFactory):
    from_asset = factory.SubFactory(AssetFactory)
    to_asset = factory.SubFactory(AssetFactory)

    interval = 24

    class Meta:
        model = "maker.SlippagePair"
