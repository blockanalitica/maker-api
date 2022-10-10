# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import csv
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from operator import itemgetter
from statistics import mean

import requests
from django.core.cache import cache
from django.db.models import Avg, Max, Min, Sum
from django.db.models.functions import TruncDay, TruncMinute

from maker.models import DAITrade
from maker.sources.cryptocompare import fetch_history_data
from maker.utils.s3 import download_csv_file_object
from maker.utils.utils import date_to_timestamp

log = logging.getLogger(__name__)

EXCHANGE_SYMBOL_MAP = {
    "USDC": "kraken",
    "TUSD": "N/A",
}


class DAITradesFetcher:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._usd_prices = defaultdict(dict)

    def _fetch_last_day_ohlcv_data(self, from_symbol, exchange):
        response = fetch_history_data(
            from_symbol, "USD", exchange, ts=None, ohlcv_type="histominute", limit=1440
        )
        return response["Data"]["Data"]

    def _fetch_ohlcv_minute_data_from_s3(self, dt, from_symbol, exchange):
        day = dt.date()
        ohlcv = []
        while day < date.today():
            filename = "ohlcv/{}/{}_{}_{}_{}_histominute.csv".format(
                from_symbol,
                day.strftime("%Y%m%d"),
                from_symbol,
                "USD",
                exchange.lower(),
            )
            day += timedelta(days=1)
            reader = download_csv_file_object(filename)
            ohlcv.extend(list(reader))
        ohlcv.extend(self._fetch_last_day_ohlcv_data(from_symbol, exchange))
        return ohlcv

    def _fetch_full_ohlcv_minute_data(self, dt, from_symbol, exchange):
        if from_symbol not in {
            "USDT",
            "USDC",
            "TUSD",
        } and dt.date() < date.today() - timedelta(days=5):
            ohlcv = self._fetch_ohlcv_minute_data_from_s3(dt, from_symbol, exchange)
        else:
            ts = None
            ohlcv = []
            while True:
                response = fetch_history_data(
                    from_symbol,
                    "USD",
                    exchange,
                    ts=ts,
                    ohlcv_type="histominute",
                    limit=2000,
                )
                if not response:
                    break
                if response["Data"]["TimeFrom"] < date_to_timestamp(
                    date.today() - timedelta(days=5)
                ):
                    break

                ts = response["Data"]["TimeFrom"]
                data = response["Data"]["Data"]
                if not data:
                    break

                ohlcv += data
        return ohlcv

    def usd_price(self, dt, from_symbol):
        timestamp = int(dt.timestamp())
        if from_symbol == "WETH":
            from_symbol = "ETH"
        exchange = EXCHANGE_SYMBOL_MAP.get(from_symbol, "coinbase")
        key = from_symbol

        if key not in self._usd_prices:
            log.debug(
                "Requesting histominute ohlcv for pair {}-USD on exchange {}".format(
                    from_symbol, exchange
                )
            )
            if dt < datetime.now() - timedelta(days=1):
                ohlcv_data = self._fetch_full_ohlcv_minute_data(
                    dt, from_symbol, exchange
                )
            else:
                ohlcv_data = self._fetch_last_day_ohlcv_data(from_symbol, exchange)

            for ohlcv in ohlcv_data:
                self._usd_prices[key][int(ohlcv["time"])] = mean(
                    [Decimal(str(ohlcv["close"])), Decimal(str(ohlcv["open"]))]
                )
        try:
            return self._usd_prices[key][timestamp]
        except KeyError as e:
            if dt < datetime.now() - timedelta(days=3) and from_symbol in {
                "USDT",
                "USDC",
                "TUSD",
            }:
                # We might not be able to fetch historical prices, so in that case,
                # use the last price (or first depending on how you look at it) that
                # we have at that time. Only use this for stablecoins otherwise it's
                # gonna be wrong
                prices = sorted(self._usd_prices[key].items(), key=lambda x: x[0])
                return prices[0][1]
            else:
                log.warning(
                    "Couldn't get price for date %s (timestamp %s) symbol %s",
                    dt,
                    timestamp,
                    from_symbol,
                    extra={"_usd_prices": self._usd_prices[key]},
                )
                log.warning("USD Prices: %s", self._usd_prices[key])
                raise e

    def fetch(self, days=30):
        filename = "combined-DAI-trades-{}d.csv".format(days)
        log.debug("Started fetching {}".format(filename))
        disk_filename = "/tmp/DAI-trades-{}.csv".format(int(datetime.now().timestamp()))
        url = "https://dai.stablecoin.science/data/{}".format(filename)
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            with open(disk_filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

        log.debug("Finished fetching {}".format(filename))

        last_trade = DAITrade.objects.all().order_by("-timestamp").first()
        if last_trade and last_trade.datetime < datetime.now() - timedelta(days=3):
            log.warning("Last stored DAITrade was on %s", last_trade.datetime)

        trades = []
        with open(disk_filename, encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            for index, row in enumerate(reader):
                if last_trade and Decimal(row["timestamp"]) <= last_trade.timestamp:
                    if index % 10000 == 0:
                        log.debug(
                            "Skipping... ({} - {} - {})".format(
                                index, row["timestamp"], last_trade.timestamp
                            )
                        )
                    continue

                dt = datetime.fromtimestamp(float(row["timestamp"]))
                amount = Decimal(row["amount"])
                price = Decimal(row["price"])

                dt_minute = dt.replace(second=0, microsecond=0)
                pair = row["pair"].split("-")
                if row["pair"] == "DAI-USD":
                    dai_price = price
                    dai_amount = amount
                elif pair[0] == "DAI":
                    if amount < 1:  # Ignore small trades
                        continue

                    dai_price = price * self.usd_price(dt_minute, pair[1])
                    dai_amount = amount
                else:
                    if amount < 0.01:  # amount ETH in DAI - ignore small trades
                        continue
                    dai_price = self.usd_price(dt_minute, pair[0]) / price
                    dai_amount = amount * price

                # Ignore DAI trades that are too far out of the intended price
                if dai_price < Decimal("0.8") or dai_price > Decimal("1.15"):
                    log.info(
                        "Skipping DAI trade because price is too far out: %s",
                        dai_price,
                        extra={
                            "dai_price": dai_price,
                            "dai_amount": dai_amount,
                            "row": row,
                        },
                    )
                    continue

                trades.append(
                    DAITrade(
                        timestamp=row["timestamp"],
                        datetime=dt,
                        pair=row["pair"],
                        exchange=row["exchange"],
                        amount=amount,
                        price=price,
                        dai_price=dai_price,
                        dai_amount=dai_amount,
                    )
                )

                if index > 0 and index % 5000 == 0:
                    log.debug("Creating DAITrade on index {}".format(index))
                    DAITrade.objects.bulk_create(trades)
                    trades = []

        # finish up the last remaining DAITrades that weren't in the full chunk
        DAITrade.objects.bulk_create(trades)

        # Cleanup after the run
        os.remove(disk_filename)


def trade_data_for_last_day():
    # Set second and microsecond to 0 so we fetch all data for the first minute while
    # grouping
    now = datetime.now().replace(second=0, microsecond=0)
    dt = now - timedelta(days=1)
    trades_query = DAITrade.objects.filter(datetime__gte=dt)
    trades = (
        trades_query.annotate(dt=TruncMinute("datetime"))
        .values("dt")
        .annotate(
            price_max=Max("dai_price"),
            price_min=Min("dai_price"),
            price_avg=Avg("dai_price"),
            amount_total=Sum("dai_amount"),
        )
        .order_by("dt")
    )

    agg = trades_query.aggregate(
        price_max=Max("dai_price"),
        price_min=Min("dai_price"),
        price_avg=Avg("dai_price"),
        amount_total=Sum("dai_amount"),
    )
    return {
        "trades": trades,
        "max": agg["price_max"],
        "min": agg["price_min"],
        "avg": agg["price_avg"],
        "amount_total": agg["amount_total"],
    }


def trade_data_daily():
    cache_key = "DAITrade.data.daily"
    cached = cache.get(cache_key)
    if cached:
        return cached

    now = date.today()
    dt = now - timedelta(days=90)
    trades_query = DAITrade.objects.filter(datetime__gte=dt)
    trades = (
        trades_query.annotate(dt=TruncDay("datetime"))
        .values("dt")
        .annotate(
            price_max=Max("dai_price"),
            price_min=Min("dai_price"),
            price_avg=Avg("dai_price"),
            amount_total=Sum("dai_amount"),
        )
        .order_by("dt")
    )
    cache.set(cache_key, trades, timeout=60 * 30)  # cache for 30 min
    return trades


def trade_volume_data(days=1):
    dt = datetime.now() - timedelta(days=days)
    trades = DAITrade.objects.filter(datetime__gte=dt).values("dai_price", "dai_amount")
    rounded_data = defaultdict(Decimal)

    for trade in trades:
        rounded_data[round(trade["dai_price"], 3)] += trade["dai_amount"]
    data = [{"price": k, "amount": v} for k, v in rounded_data.items()]
    return sorted(data, key=itemgetter("price"))


def trade_volume_data_per_exchange(days=1):
    dt = datetime.now() - timedelta(days=days)
    trades = DAITrade.objects.filter(datetime__gte=dt).values(
        "dai_price", "dai_amount", "exchange"
    )
    rounded_data = defaultdict(lambda: defaultdict(Decimal))
    for trade in trades:
        rounded_data[trade["exchange"]][round(trade["dai_price"], 3)] += trade[
            "dai_amount"
        ]

    data = []
    for exchange, prices in rounded_data.items():
        for price, amount in prices.items():
            data.append({"exchange": exchange, "price": price, "amount": amount})
    return sorted(data, key=itemgetter("exchange"))


def get_stats():
    dt_yesterday = datetime.now().replace(second=0, microsecond=0) - timedelta(days=1)
    last_24hr = DAITrade.objects.filter(datetime__gte=dt_yesterday).aggregate(
        price_max=Max("dai_price"),
        price_min=Min("dai_price"),
        price_avg=Avg("dai_price"),
        amount_total=Sum("dai_amount"),
    )

    dt_week_ago = datetime.now() - timedelta(days=7)
    last_7days = DAITrade.objects.filter(datetime__gte=dt_week_ago).aggregate(
        price_max=Max("dai_price"),
        price_min=Min("dai_price"),
        price_avg=Avg("dai_price"),
        amount_total=Sum("dai_amount"),
    )

    exchange_stats_last_7days = (
        DAITrade.objects.filter(datetime__gte=dt_week_ago)
        .values("exchange")
        .annotate(
            max=Max("dai_price"),
            min=Min("dai_price"),
            avg=Avg("dai_price"),
            amount_total=Sum("dai_amount"),
        )
        .order_by("exchange")
    )
    return {
        "last_24h": {
            "max": last_24hr["price_max"],
            "min": last_24hr["price_min"],
            "avg": last_24hr["price_avg"],
            "amount_total": last_24hr["amount_total"],
        },
        "last_7days": {
            "max": last_7days["price_max"],
            "min": last_7days["price_min"],
            "avg": last_7days["price_avg"],
            "amount_total": last_7days["amount_total"],
            "exchange_stats": list(exchange_stats_last_7days),
        },
    }
