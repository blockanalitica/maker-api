# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from statistics import mean

from requests.exceptions import RetryError

from maker.constants import LIQUIDITY_COLLATERAL_ASSET_MAP
from maker.models import Asset, SlippageDaily, SlippagePair
from maker.sources.oneinch import get_oneinch_quote
from maker.sources.zerox import get_zerox_quote
from maker.utils.utils import get_date_days_ago, get_today_timestamp

log = logging.getLogger(__name__)


def _generate_usd_amounts():
    step = 10000
    x = 0
    usd_amounts = []
    while x < 5000000000:
        x += step
        usd_amounts.append(x)
        if x == 100000:
            step = 100000
        elif x == 1000000:
            step = 1000000
        elif x == 10000000:
            step = 5000000
        elif x == 100000000:
            step = 10000000
    return usd_amounts


def save_oneinch_slippages(slippage_pair_id):
    slippage_pair = SlippagePair.objects.get(id=slippage_pair_id)
    timestamp = get_today_timestamp()
    from_asset = slippage_pair.from_asset
    from_asset_mantissa = Decimal(str(10**from_asset.decimals))
    to_asset = slippage_pair.to_asset
    to_asset_address = to_asset.address
    to_asset_mantissa = Decimal(str(10**to_asset.decimals))
    usd_amounts = _generate_usd_amounts()

    retry_errors = 0
    for usd_amount in usd_amounts:
        log.debug(
            f"Creating slippage slippage for: "
            f"{slippage_pair.from_asset.symbol}-{usd_amount}"
        )
        asset_price = from_asset.price

        asset_amount = str(int(usd_amount / asset_price * from_asset_mantissa))
        try:
            quote = get_oneinch_quote(
                from_asset.address, to_asset_address, asset_amount
            )
        except RetryError:
            retry_errors += 1
            log.exception(
                "RetryError get_quote_data(%s, %s, %s), usd_amount: %s",
                slippage_pair.from_asset.symbol,
                slippage_pair.to_asset.symbol,
                asset_amount,
                usd_amount,
            )
            if retry_errors > 5:
                log.exception(
                    "Got 5 retry errors in a row. Stopped updating slippage pair %s",
                    slippage_pair_id,
                )
                break
            continue

        # Reset number of errors
        retry_errors = 0

        slippage = (
            Decimal(quote["toTokenAmount"]) / to_asset_mantissa * 100
        ) / usd_amount - 100

        if slippage > Decimal("100"):
            continue

        slippage_daily, _ = SlippageDaily.objects.get_or_create(
            pair=slippage_pair,
            timestamp=timestamp,
            date=date.today(),
            usd_amount=usd_amount,
            source="oneinch",
        )
        slippage_daily.slippage_list.append(slippage)
        slippage_daily.slippage_percent_avg = mean(slippage_daily.slippage_list)
        slippage_daily.save()
        if slippage < -80:
            break
        time.sleep(0.5)
    slippage_pair.last_run = datetime.utcnow()
    slippage_pair.save()


def save_zerox_slippages(slippage_pair):
    timestamp = get_today_timestamp()

    from_asset = slippage_pair.from_asset
    to_asset = slippage_pair.to_asset
    to_asset_address = to_asset.address
    from_asset_mantissa = Decimal(str(10**from_asset.decimals))
    asset_price = from_asset.price
    usd_amounts = _generate_usd_amounts()
    for usd_amount in usd_amounts:
        log.debug(
            f"Creating slippage slippage for: "
            f"{slippage_pair.from_asset.symbol}-{usd_amount}"
        )

        asset_amount = str(int((usd_amount / asset_price * from_asset_mantissa)))

        try:
            quote = get_zerox_quote(from_asset.address, to_asset_address, asset_amount)
        except RetryError:
            log.exception(
                "RetryError get_quote_data(%s, %s, %s), usd_amount: %s",
                slippage_pair.from_asset.symbol,
                slippage_pair.to_asset.symbol,
                asset_amount,
                usd_amount,
            )
            continue
        slippage = ((asset_price - Decimal(quote["price"])) / asset_price) * -100
        if slippage > Decimal("100"):
            continue

        slippage_daily, _ = SlippageDaily.objects.get_or_create(
            pair=slippage_pair,
            timestamp=timestamp,
            date=date.today(),
            usd_amount=usd_amount,
            source="zerox",
        )
        slippage_daily.slippage_list.append(slippage)
        slippage_daily.slippage_percent_avg = mean(slippage_daily.slippage_list)
        slippage_daily.save()
        if slippage < -90:
            break

    slippage_pair.last_run = datetime.utcnow()
    slippage_pair.save()


def get_slippage_history(asset, source):
    dates = {
        "Today": None,
        "1 week ago": get_date_days_ago(number_of_days=7),
        "1 month ago": get_date_days_ago(number_of_days=30),
        "2 months ago": get_date_days_ago(number_of_days=60),
        "3 months ago": get_date_days_ago(number_of_days=90),
    }

    table_data = {}
    for key, for_date in dates.items():
        table_data.update(
            get_slippage_from_asset(asset, source, for_date=for_date, extra_key=key)
        )
    return table_data


def get_slippage_from_asset(asset, source, for_date=None, extra_key=None):
    if for_date:
        slippages = (
            SlippageDaily.objects.filter(
                pair__from_asset=asset, source=source, date=for_date
            )
            .select_related("pair", "pair__from_asset", "pair__to_asset")
            .values(
                "usd_amount",
                "pair__from_asset__symbol",
                "pair__to_asset__symbol",
                "slippage_percent_avg",
            )
            .order_by("usd_amount")
        )
    else:
        slippages = (
            SlippageDaily.objects.filter(
                pair__from_asset=asset, source=source, is_active=True
            )
            .select_related("pair", "pair__from_asset", "pair__to_asset")
            .values(
                "usd_amount",
                "pair__from_asset__symbol",
                "pair__to_asset__symbol",
                "slippage_percent_avg",
            )
            .order_by("usd_amount")
        )
    table_data = defaultdict(dict)
    for slippage in slippages:
        if not slippage["slippage_percent_avg"]:
            continue
        fa = slippage["pair__from_asset__symbol"]
        ta = slippage["pair__to_asset__symbol"]
        pair = f"{fa}-{ta}"
        if extra_key:
            pair = f"{pair} {extra_key}"
        table_data[pair][slippage["usd_amount"]] = round(
            slippage["slippage_percent_avg"], 2
        )
    return table_data


def get_slippage_to_dai(symbol, usd_amount):
    if symbol == "ETH":
        symbol = "WETH"
    if symbol == "WSTETH":
        symbol = "stETH"

    daily_slippage = (
        SlippageDaily.objects.filter(
            pair__from_asset__symbol=symbol,
            usd_amount__gte=usd_amount,
            is_active=True,
        )
        .order_by("usd_amount")
        .first()
    )

    slippage_percent = daily_slippage.slippage_percent_avg
    return slippage_percent


def get_slippage_for_lp(lp_symbol, usd_amount):
    if usd_amount is None:
        return
    asset_symbols = LIQUIDITY_COLLATERAL_ASSET_MAP[lp_symbol]
    slippages = []
    for symbol in asset_symbols:
        asset = Asset.objects.get(symbol=symbol)
        if asset.type == "stable":
            continue
        daily_slippage = (
            SlippageDaily.objects.filter(
                pair__from_asset=asset,
                usd_amount__gte=usd_amount / 2,
                is_active=True,
            )
            .order_by("usd_amount")
            .first()
        )
        slippages.append(daily_slippage.slippage_percent_avg)
    if len(slippages) > 0:
        slippage_percent = sum(slippages) / len(slippages)
    else:
        slippage_percent = 0
    return slippage_percent
