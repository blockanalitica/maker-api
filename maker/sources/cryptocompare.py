# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
import time
from datetime import date, timedelta
from json import JSONDecodeError

from django.conf import settings

from maker.utils.http import retry_get_json
from maker.utils.utils import get_date_timestamp_eod

log = logging.getLogger(__name__)


def fetch_history_data(
    symbol, pair_symbol, exchange, ts, limit=2000, ohlcv_type="histoday"
):
    params = {
        "fsym": symbol,
        "tsym": pair_symbol,
        "limit": limit,
        "toTs": int(ts) if ts is not None else None,
    }
    url = f"https://min-api.cryptocompare.com/data/v2/{ohlcv_type}"
    if exchange == "N/A":
        params["tryConversion"] = "true"
    else:
        params["tryConversion"] = "false"
        params["e"] = exchange
    headers = {"authorization": f"Apikey {settings.CRYPTOCOMPARE_API_KEY}"}

    retries = 1
    while retries < 6:
        try:
            content = retry_get_json(url, params=params, headers=headers)
        except JSONDecodeError:
            log.error("Could not fetch_history_data")

        if content["Response"] == "Error" and not content["Data"]:
            time.sleep(retries * 2)
            retries += 1
        else:
            break

    if content["Response"] == "Error" and (
        content.get("ParamWithError") == "e"
        or content.get("ParamWithError") == "toTs"
        or not content["Data"]
    ):
        return None

    return content


def get_prices(symbols):
    symbol_string = ",".join(symbols)
    url = f"https://min-api.cryptocompare.com/data/pricemulti?fsyms={symbol_string}&tsyms=USD"
    headers = {"authorization": f"Apikey {settings.CRYPTOCOMPARE_API_KEY}"}
    content = retry_get_json(url, headers=headers)
    return content


def fetch_pair_mapping(symbol):
    url = "https://min-api.cryptocompare.com/data/pair/mapping/fsym"
    params = {"fsym": symbol}
    headers = {"authorization": f"Apikey {settings.CRYPTOCOMPARE_API_KEY}"}
    content = retry_get_json(url, params=params, headers=headers)
    data = content["Data"]
    return data


def fetch_full_history(
    symbol, pair_symbol, exchange, ts=None, ohlcv_type="histoday", number_of_days=90
):
    """
    Returns a history between ts and ts + number_of_days.

    :param ts: timestamp up to which the records will be returned
    :param number_of_days: 0 returns today's data, 1 returns yesterday's data and so on
    """
    all_data = []
    if not ts:
        yesterday = date.today() - timedelta(days=1)
        ts = get_date_timestamp_eod(yesterday)

    from_timestamp = ts - 60 * 60 * 24 * number_of_days
    to_timestamp = ts
    while True:
        response = fetch_history_data(
            symbol,
            pair_symbol,
            exchange,
            to_timestamp,
            limit=2000,
            ohlcv_type=ohlcv_type,
        )
        if not response:
            break

        data = response["Data"]["Data"]
        if not data:
            break

        ts = response["Data"]["TimeFrom"]
        # Endpont returns the time including the to_timestamp time, so we substract 1
        # so it doesn't return the time that was included in the previous response
        to_timestamp = ts - 1

        if from_timestamp > ts:
            # Attach last few rows unill the time exceeds the from_timestamp
            for row in data:
                if row["time"] > from_timestamp:
                    all_data.append(row)
            break
        else:
            # add data to the start as it's returned time ascending
            all_data = data + all_data

    return all_data
