# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

from maker.models import PoolInfo, TokenPriceHistory
from maker.sources.subgraph import get_pair_day_data, get_pair_day_data_curve
from maker.utils.utils import get_yesterday_timestamp


def _save_yesterdays_pool_info_for_curve(pool):
    data = get_pair_day_data_curve(pool.contract_address)
    data = data[0]
    eth_price = TokenPriceHistory.objects.filter(underlying_symbol="ETH").latest().price
    total_reserve_usd = 0
    for asset_data in data.get("coins", []):
        symbol = asset_data["token"]["symbol"].upper()
        if symbol == "STETH":
            symbol = "stETH"

        price = (
            TokenPriceHistory.objects.filter(underlying_symbol=symbol).latest().price
        )
        total_reserve_usd += Decimal(asset_data["balance"]) * Decimal(price)

    yesterday_timestamp = get_yesterday_timestamp()
    for volume in data["dailyVolumes"]:
        if volume["timestamp"] == str(yesterday_timestamp):
            PoolInfo.objects.get_or_create(
                pool=pool,
                timestamp=yesterday_timestamp,
                defaults={
                    "reserve_usd": total_reserve_usd,
                    "datetime": datetime.fromtimestamp(yesterday_timestamp),
                    "volume_usd": Decimal(volume["volume"]) * eth_price,
                },
            )
            break


def _save_pool_info_dex(pool):
    data = get_pair_day_data(pool.contract_address, pool.exchange)
    try:
        last_timestamp = PoolInfo.objects.filter(pool=pool).latest().timestamp
    except PoolInfo.DoesNotExist:
        last_timestamp = None
    for item in data:
        if last_timestamp and last_timestamp >= item["date"]:
            break
        PoolInfo.objects.get_or_create(
            pool=pool,
            timestamp=item["date"],
            defaults={
                "total_supply": item["total_supply"],
                "reserve_usd": item["reserve_USD"],
                "volume_usd": item["volume_USD"],
                "tx_count": item["tx_count"],
                "datetime": datetime.fromtimestamp(item["date"]),
            },
        )


def save_pool_info(pool):
    if pool.exchange == "Curve":
        _save_yesterdays_pool_info_for_curve(pool)
    else:
        _save_pool_info_dex(pool)
