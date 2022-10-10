# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

import pytest

from maker.models import DAITrade
from maker.modules.dai_trades import DAITradesFetcher
from tests.maker.factories import DAITradeFactory


class TestDAITradesFetcher:
    @pytest.mark.django_db
    def test_fetch_adds_all_new_records(self, responses, monkeypatch):
        body = (
            "timestamp,pair,exchange,amount,price\n"
            "1631191736.563,DAI-USD,coinbase,43.2841200000000,1.000053000000000000\n"
            "1631191736.962,DAI-USD,coinbase,114.736600000000,1.000058000000000000\n"
            "1631191843.001,DAI-USD,coinbase,17.1307800000000,1.000053000000000000\n"
            "1631191843.17,ETH-DAI,ethfinex,0.04,3422.66488688092548\n"
            "1631191843.17,ETH-DAI,ethfinex,0.000666374782626900,3422.66488688092548\n"
        )

        responses.add(
            responses.GET,
            "https://dai.stablecoin.science/data/combined-DAI-trades-30d.csv",
            status=200,
            body=body,
        )

        fetcher = DAITradesFetcher()

        monkeypatch.setattr(
            fetcher,
            "_usd_prices",
            {"ETH": {1631191800: Decimal("3420")}},
        )

        fetcher.fetch()

        trades = DAITrade.objects.all().order_by("id")
        assert trades.count() == 4

        assert trades[0].timestamp == Decimal("1631191736.563")
        assert trades[0].datetime == datetime(2021, 9, 9, 12, 48, 56, 563000)
        assert trades[0].pair == "DAI-USD"
        assert trades[0].exchange == "coinbase"
        assert trades[0].amount == Decimal("43.28412")
        assert trades[0].price == Decimal("1.000053")
        assert trades[0].dai_amount == Decimal("43.28412")
        assert trades[0].dai_price == Decimal("1.000053")

        assert trades[1].timestamp == Decimal("1631191736.962")
        assert trades[1].datetime == datetime(2021, 9, 9, 12, 48, 56, 962000)
        assert trades[1].pair == "DAI-USD"
        assert trades[1].exchange == "coinbase"
        assert trades[1].amount == Decimal("114.7366")
        assert trades[1].price == Decimal("1.000058")
        assert trades[1].dai_amount == Decimal("114.7366")
        assert trades[1].dai_price == Decimal("1.000058")

        assert trades[2].timestamp == Decimal("1631191843.001")
        assert trades[2].datetime == datetime(2021, 9, 9, 12, 50, 43, 1000)
        assert trades[2].pair == "DAI-USD"
        assert trades[2].exchange == "coinbase"
        assert trades[2].amount == Decimal("17.13078")
        assert trades[2].price == Decimal("1.000053")
        assert trades[2].dai_amount == Decimal("17.13078")
        assert trades[2].dai_price == Decimal("1.000053")

        assert trades[3].timestamp == Decimal("1631191843.17")
        assert trades[3].datetime == datetime(2021, 9, 9, 12, 50, 43, 170000)
        assert trades[3].pair == "ETH-DAI"
        assert trades[3].exchange == "ethfinex"
        assert trades[3].amount == Decimal("0.040000000000000000")
        assert trades[3].price == Decimal("3422.66488688092548")
        assert trades[3].dai_amount == Decimal("136.906595475237019200")
        assert trades[3].dai_price == Decimal("0.999221400000000003")

    @pytest.mark.django_db
    def test_fetch_only_after_last_timestamp_record(self, responses, monkeypatch):
        body = (
            "timestamp,pair,exchange,amount,price\n"
            "1631191736.563,DAI-USD,coinbase,43.284120000000000,1.000053000000000000\n"
            "1631191736.962,DAI-USD,coinbase,114.73660000000000,1.000058000000000000\n"
            "1631191843.001,DAI-USD,coinbase,17.130780000000000,1.000053000000000000\n"
            "1631191843.17,ETH-DAI,ethfinex,0.04,3422.66488688092548\n"
            "1631191843.17,ETH-DAI,ethfinex,0.000666374782626900,3422.66488688092548\n"
        )

        responses.add(
            responses.GET,
            "https://dai.stablecoin.science/data/combined-DAI-trades-30d.csv",
            status=200,
            body=body,
        )

        DAITradeFactory(timestamp=Decimal("1631191736.962"))

        fetcher = DAITradesFetcher()
        monkeypatch.setattr(
            fetcher,
            "_usd_prices",
            {"ETH": {1631191800: Decimal("3420")}},
        )
        fetcher.fetch()

        trades = DAITrade.objects.all().order_by("id")
        assert trades.count() == 3

        assert trades[1].timestamp == Decimal("1631191843.001")
        assert trades[1].datetime == datetime(2021, 9, 9, 12, 50, 43, 1000)
        assert trades[1].pair == "DAI-USD"
        assert trades[1].exchange == "coinbase"
        assert trades[1].amount == Decimal("17.13078")
        assert trades[1].price == Decimal("1.000053")

        assert trades[2].timestamp == Decimal("1631191843.17")
        assert trades[2].datetime == datetime(2021, 9, 9, 12, 50, 43, 170000)
        assert trades[2].pair == "ETH-DAI"
        assert trades[2].exchange == "ethfinex"
        assert trades[2].amount == Decimal("0.040000000000000000")
        assert trades[2].price == Decimal("3422.66488688092548")

    @pytest.mark.django_db
    def test_fetch_ignores_big_dai_price_discrepancies(self, responses, monkeypatch):
        body = (
            "timestamp,pair,exchange,amount,price\n"
            "1631191736.563,DAI-USD,coinbase,43.2841200000000,1.000053000000000000\n"
            "1631191736.962,DAI-USD,coinbase,114.736600000000,1.151\n"
            "1631191843.001,DAI-USD,coinbase,17.1307800000000,0.79999\n"
            "1631191843.17,ETH-DAI,ethfinex,0.04,22.66488688092548\n"
            "1631191843.17,ETH-DAI,ethfinex,0.000666374782626900,34222222.664886\n"
        )

        responses.add(
            responses.GET,
            "https://dai.stablecoin.science/data/combined-DAI-trades-30d.csv",
            status=200,
            body=body,
        )

        fetcher = DAITradesFetcher()

        monkeypatch.setattr(
            fetcher,
            "_usd_prices",
            {"ETH": {1631191800: Decimal("3420")}},
        )

        fetcher.fetch()

        trades = DAITrade.objects.all()
        assert trades.count() == 1

        assert trades[0].timestamp == Decimal("1631191736.563")
        assert trades[0].datetime == datetime(2021, 9, 9, 12, 48, 56, 563000)
        assert trades[0].pair == "DAI-USD"
        assert trades[0].exchange == "coinbase"
        assert trades[0].amount == Decimal("43.28412")
        assert trades[0].price == Decimal("1.000053")
        assert trades[0].dai_amount == Decimal("43.28412")
        assert trades[0].dai_price == Decimal("1.000053")
