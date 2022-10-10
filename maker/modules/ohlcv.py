# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import csv
import io
import logging
import math
import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal
from operator import itemgetter

import pytz
from django.db.models import Avg

from maker.constants import (
    DRAWDOWN_PAIRS_HISTORY_DAYS,
    EXCHANGES,
    OHLCV_TYPE_DAILY,
    STABLECOINS,
)
from maker.models import OHLCV, OHLCVPair
from maker.sources.cryptocompare import fetch_full_history, fetch_pair_mapping
from maker.utils.s3 import upload_content_to_s3
from maker.utils.utils import get_date_timestamp_days_ago, get_date_timestamp_eod

log = logging.getLogger(__name__)


def get_available_pairs_for_asset_symbol(symbol):
    data = fetch_pair_mapping(symbol)
    whitelisted_exchanges = list(EXCHANGES.keys())
    to_asset = [
        "USD",
        "EUR",
        "GBP",
        "AUD",
        "CAD",
        "CHF",
        "JPY",
        "KRW",
        "USDT",
        "USDC",
        "DAI",
        "PAX",
        "GUSD",
        "BUSD",
        "HUSD",
        "TUSD",
        "SUSD",
        "ETH",
        "BTC",
    ]
    pairs = []
    for item in data:
        if (
            item["exchange"] in whitelisted_exchanges
            and item["tsym"].upper() in to_asset
        ):
            pairs.append(item)
    return pairs


def sync_ohlcv_asset_pairs(symbol):
    if symbol in {"WBTC", "WSTETH"}:
        symbol = symbol[1:]

    log.debug("Syncing OHLCVPair for symbol %s", symbol)
    pairs = get_available_pairs_for_asset_symbol(symbol)
    for pair in pairs:
        to_asset_symbol = pair["tsym"].upper()
        to_asset_is_stable = to_asset_symbol == "USD" or to_asset_symbol in STABLECOINS

        OHLCVPair.objects.get_or_create(
            from_asset_symbol=symbol,
            to_asset_symbol=to_asset_symbol,
            exchange=pair["exchange"],
            ohlcv_type=OHLCV_TYPE_DAILY,
            defaults={
                "to_asset_is_stable": to_asset_is_stable,
                "is_active": True,
            },
        )


def sync_history_for_ohlcv_pair(pair):
    number_of_days = DRAWDOWN_PAIRS_HISTORY_DAYS.get(
        "{}-{}-{}-{}".format(
            pair.from_asset_symbol,
            pair.to_asset_symbol,
            pair.exchange,
            pair.ohlcv_type,
        ),
        90,
    )
    log.debug("Syncing history for pair %s", pair)
    _save_latest_ohlcv(pair, number_of_days)


def _save_latest_ohlcv(pair, number_of_days):
    ohlcv_data = fetch_full_history(
        pair.from_asset_symbol,
        pair.to_asset_symbol,
        pair.exchange,
        ohlcv_type=pair.ohlcv_type,
        number_of_days=number_of_days,
    )
    if not ohlcv_data:
        return

    _save_asset_pair_ohlcv(pair, ohlcv_data, number_of_days=number_of_days)


def _save_asset_pair_ohlcv(pair, ohlcv_data, number_of_days):
    from_timestamp = get_date_timestamp_days_ago(number_of_days)
    try:
        last_timestamp = OHLCV.objects.filter(pair=pair).latest().timestamp
    except OHLCV.DoesNotExist:
        last_timestamp = None

    # needs to be reversed, in response it is ordered by asc timestamp.
    # We want first entry to be latest
    ohlcv_data = list(reversed(sorted(ohlcv_data, key=itemgetter("time"))))

    conversion_pairs = None
    if not pair.to_asset_is_stable:
        conversion_pairs = OHLCVPair.objects.filter(
            from_asset_symbol=pair.to_asset_symbol, to_asset_symbol="USD"
        )
        # check if conversion pair is updated for that timestamp
        # if it is not first fetch data from conversion_pairs and the continue with
        # pair data
        lastest_timestamp_from_ohlcv_data = ohlcv_data[0]["time"]
        for conversion_pair in conversion_pairs:
            ohlcv_exists = OHLCV.objects.filter(
                timestamp=lastest_timestamp_from_ohlcv_data, pair=conversion_pair
            ).exists()
            if not ohlcv_exists:
                _save_latest_ohlcv(conversion_pair, number_of_days=number_of_days)

    if pair.exchange in EXCHANGES:
        haircut = Decimal(EXCHANGES[pair.exchange]["haircut"] / 100)
    else:
        haircut = Decimal("100")

    to_create = []
    for ohlcv in ohlcv_data:
        # dont get ohlcv data from today since they are not complete
        if ohlcv["close"] == 0:
            continue
        if last_timestamp and ohlcv["time"] <= last_timestamp:
            break
        if from_timestamp > ohlcv["time"]:
            break

        volumen_to = ohlcv["volumeto"]
        if volumen_to is None:
            continue

        if pair.to_asset_is_stable:
            volume_usd = Decimal(volumen_to) * haircut
        else:
            usd_history = (
                OHLCV.objects.filter(timestamp=ohlcv["time"], pair__in=conversion_pairs)
                .values("timestamp")
                .annotate(close_avg=Avg("close"))
                .first()
            )
            if not usd_history:
                log.warning(
                    "No USD conversion pair for pair: %s - %s (%s)",
                    pair.from_asset_symbol,
                    pair.to_asset_symbol,
                    pair.exchange,
                )
                continue

            usd_price = usd_history["close_avg"]
            volume_usd = (Decimal(volumen_to) * usd_price) * haircut

        drawdown = (ohlcv["close"] * 100) / ohlcv["open"] - 100
        drawdown_hl = drawdown
        if ohlcv["low"] and ohlcv["high"]:
            drawdown_hl = (ohlcv["low"] * 100) / ohlcv["high"] - 100

        to_create.append(
            OHLCV(
                pair=pair,
                ohlcv_type=pair.ohlcv_type,
                timestamp=ohlcv["time"],
                datetime=datetime.fromtimestamp(ohlcv["time"]),
                close=ohlcv["close"],
                high=ohlcv["high"],
                low=ohlcv["low"],
                open=ohlcv["open"],
                volume_from=ohlcv["volumefrom"],
                volume_to=volumen_to,
                volume_usd=volume_usd,
                drawdown=drawdown,
                drawdown_hl=drawdown_hl,
            )
        )

    if to_create:
        log.debug("Creating %s OHLCV records for %s", len(to_create), pair)
        OHLCV.objects.bulk_create(to_create)


def calculate_volatility(ohlcv_pair, trailing_days=90, for_date=None):
    if not for_date:
        for_date = datetime.now()
    dt_from = for_date - timedelta(days=trailing_days)
    drawdowns = OHLCV.objects.filter(
        pair=ohlcv_pair, datetime__gte=dt_from, datetime__date__lte=for_date
    ).values_list("drawdown", flat=True)
    if not drawdowns:
        return
    std = statistics.pstdev(drawdowns)
    return std * Decimal(math.sqrt(24))


def _history_to_csv(history):
    fieldnames = [
        "date",
        "time",
        "close",
        "high",
        "low",
        "open",
        "volumefrom",
        "volumeto",
        "conversionType",
        "conversionSymbol",
    ]
    with io.StringIO() as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in history:
            row["date"] = datetime.fromtimestamp(row["time"], tz=pytz.UTC)
            writer.writerow(row)

        return output.getvalue()


def save_yesterdays_histominute_ohlcv(symbol, pair_symbol, exchange_name):
    day = date.today() - timedelta(days=1)
    ts = get_date_timestamp_eod(day)
    data = fetch_full_history(
        symbol,
        pair_symbol,
        exchange_name,
        ts=ts,
        ohlcv_type="histominute",
        number_of_days=1,
    )

    content = _history_to_csv(data)
    filename = "{}_{}_{}_{}_histominute.csv".format(
        day.strftime("%Y%m%d"), symbol, pair_symbol, exchange_name.lower()
    )
    upload_content_to_s3(content, "ohlcv/{}/{}".format(symbol, filename))
