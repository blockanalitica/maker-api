# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Value
from django_bulk_load import bulk_insert_models
from eth_utils import to_checksum_address
from web3 import Web3

from maker.models import TokenPriceHistory
from maker.modules.block import get_or_save_block
from maker.utils.blockchain.chain import Blockchain
from maker.utils.utils import date_to_timestamp

from ..models import OSM, MakerAsset, Medianizer, OSMDaily

log = logging.getLogger(__name__)


def _convert_price(hex_price):
    return Decimal(int(hex_price[34:], 16)) / 10**18


def _get_osm_price(address, block_number, chain):
    address = Web3.toChecksumAddress(address)
    next_price = chain.eth.get_storage_at(
        address, 4, block_identifier=block_number
    ).hex()
    current_price = chain.eth.get_storage_at(
        address, 3, block_identifier=block_number
    ).hex()
    return _convert_price(current_price), _convert_price(next_price)


def get_next_osm_price(asset, block_number, chain):
    next_price = Decimal("0")
    current_price = Decimal("0")
    if asset.type in ["asset", "lp"]:
        current_price, next_price = _get_osm_price(
            Web3.toChecksumAddress(asset.oracle_address), block_number, chain
        )
    block = get_or_save_block(block_number)
    return current_price, next_price, block.timestamp


def fetch_block_numbers_from_poke_events(asset, from_block=None, chain=None):
    if asset.type == "lp":
        topic = Web3.keccak(text="Value(uint128,uint128)").hex()
    else:
        topic = Web3.keccak(text="LogValue(bytes32)").hex()
    step = 50000
    end_block = chain.get_latest_block()
    for block_number in range(from_block, end_block, step):
        filters = {
            "fromBlock": block_number,
            "toBlock": block_number + step,
            "address": Web3.toChecksumAddress(asset.oracle_address),
            "topics": [topic],
        }
        events = chain.eth.get_logs(filters)
        block_numbers = set()
        for event in events:
            block_numbers.add(event["blockNumber"])
        # Order block numbers from earliest to lastest
        yield sorted(block_numbers)


def save_osm_for_asset(symbol, last_block=None):
    chain = Blockchain(node=settings.ETH_NODE_MAKER)
    asset = MakerAsset.objects.get(symbol=symbol)
    if not last_block:
        try:
            last_block = OSM.objects.latest_for_asset(asset.symbol).block_number + 1
        except OSM.DoesNotExist:
            last_block = 8936795

    for block_numbers in fetch_block_numbers_from_poke_events(asset, last_block, chain):
        bulk_create = []
        for block_number in block_numbers:
            current_price, next_price, timestamp = get_next_osm_price(
                asset, block_number, chain
            )
            bulk_create.append(
                OSM(
                    symbol=asset.symbol,
                    block_number=block_number,
                    timestamp=timestamp,
                    datetime=datetime.fromtimestamp(timestamp),
                    current_price=current_price,
                    next_price=next_price,
                )
            )
        if not bulk_create:
            continue
        bulk_insert_models(bulk_create, ignore_conflicts=True)


def get_medianizer_address(oracle_address, chain=None):
    chain = Blockchain(_web3=chain, node=settings.ETH_NODE_MAKER)
    token_calls = [
        (
            oracle_address,
            [
                "src()(address)",
            ],
            ["medianizer_address", None],
        )
    ]

    data = chain.call_multicall(token_calls)
    return data["medianizer_address"]


def save_medianizer_prices(symbol, medianizer_address, chain=None, from_block=0):
    chain = Blockchain(node=settings.ETH_NODE_MAKER)
    medianizer_address = to_checksum_address(medianizer_address)
    topic = chain.to_hex_topic("LogMedianPrice(uint256,uint256)")
    end_block = chain.get_latest_block()
    step = 50000
    for block_number in range(from_block, end_block, step):
        bulk_create = []
        if block_number + step > end_block:
            end_block = "latest"
        filters = {
            "fromBlock": block_number,
            "toBlock": end_block,
            "address": medianizer_address,
            "topics": [topic],
        }
        events = chain.eth.get_logs(filters)
        block_numbers = set()
        for event in events:
            block_numbers.add(event["blockNumber"])
        blocks = sorted(block_numbers)
        for block_number in blocks:
            hex_value = chain.get_storage_at(
                medianizer_address, 1, block_identifier=block_number
            )
            price = chain.covert_to_number(hex_value) / Decimal(10**18)
            block = get_or_save_block(block_number)
            bulk_create.append(
                Medianizer(
                    symbol=symbol,
                    price=price,
                    block_number=block.block_number,
                    timestamp=block.timestamp,
                    datetime=block.datetime,
                )
            )
        if not bulk_create:
            continue
        bulk_insert_models(bulk_create, ignore_conflicts=True)


def get_osm_and_medianizer(symbol):
    osm = OSM.objects.filter(symbol=symbol).latest()

    medianizer_price = None
    medianizer_datetime = None
    medianizer_diff = None
    medianizers = Medianizer.objects.filter(symbol=symbol).order_by("-block_number")[:2]
    if len(medianizers) > 0:
        medianizer_price = medianizers[0].price
        medianizer_datetime = medianizers[0].datetime
    if len(medianizers) > 1:
        medianizer_diff = round(
            ((medianizer_price - medianizers[1].price) / medianizers[1].price * 100), 2
        )

    change_price = (
        False
        if osm.current_price == osm.next_price and osm.next_price == medianizer_price
        else True
    )
    diff = round(((osm.next_price - osm.current_price) / osm.current_price * 100), 2)
    last_updated = osm.datetime
    to_next_change = None
    if change_price:
        diff_time = datetime.utcnow() - last_updated
        to_next_change = int((60 * 60 - diff_time.seconds) / 60)

    data = {
        "osm_current_price": osm.current_price,
        "osm_next_price": osm.next_price,
        "medianizer": medianizer_price,
        "medianizer_diff": medianizer_diff,
        "medianizer_datetime": medianizer_datetime,
        "datetime": osm.datetime,
        "to_next_change": to_next_change,
        "symbol": osm.symbol,
        "diff": diff,
    }
    return data


def get_price_history(symbol, days_ago):
    data = []
    underyling_symbol = symbol
    if symbol == "ETH":
        underyling_symbol = "WETH"
    if days_ago == 0:
        timestamp = 0
    else:
        timestamp = (datetime.now() - timedelta(days=days_ago)).timestamp()
    osm_history = (
        OSM.objects.annotate(key=Value("OSM"), amount=F("current_price"))
        .filter(symbol=symbol, timestamp__gte=timestamp)
        .values("key", "timestamp", "amount")
    )
    medianizer_history = (
        Medianizer.objects.annotate(key=Value("medianizer"), amount=F("price"))
        .filter(symbol=symbol, timestamp__gte=timestamp)
        .values("key", "timestamp", "amount")
    )

    chainlink_history = (
        TokenPriceHistory.objects.annotate(key=Value("chainlink"), amount=F("price"))
        .filter(underlying_symbol=underyling_symbol, timestamp__gte=timestamp)
        .values("key", "timestamp", "amount")
    )
    data.extend(osm_history)
    data.extend(medianizer_history)
    data.extend(chainlink_history)
    return data


def _get_greatest_drop_from_price_list(price_list):
    daily_high = max(price_list)
    daily_low = min(price_list)
    low = None
    greatest_drop = None
    drop_start = None
    drop_end = None

    for price in reversed(price_list):
        if low is None or price < low:
            low = price

        drop = (low - price) / price * 100
        if greatest_drop is None or drop < greatest_drop:
            greatest_drop = drop
            drop_start = price
            drop_end = low

    return daily_low, daily_high, greatest_drop, drop_start, drop_end


def save_osm_daily():
    for asset in MakerAsset.objects.filter(is_active=True):
        log.info("Saving OSMDaily for %s", asset.symbol)
        end_date = date.today()
        try:
            latest_daily = OSMDaily.objects.filter(symbol=asset.symbol).latest()
            start_date = latest_daily.date
        except OSMDaily.DoesNotExist:
            start_date = (
                OSM.objects.filter(symbol=asset.symbol).earliest().datetime.date()
            )

        days_diff = (end_date - start_date).days

        for d in range(1, days_diff + 1):
            day = start_date + timedelta(days=d)
            osms = OSM.objects.filter(symbol=asset.symbol, datetime__date=day).order_by(
                "datetime"
            )
            osms = list(osms)
            if len(osms) < 2:
                continue
            daily_open = osms[0].current_price
            daily_close = osms[-1].next_price
            if daily_open == 0:
                continue
            daily_drawdown = (daily_close - daily_open) / daily_open * 100
            price_list = [daily_open]
            for osm in osms:
                price_list.append(osm.next_price)

            (
                daily_low,
                daily_high,
                greatest_drop,
                drop_start,
                drop_end,
            ) = _get_greatest_drop_from_price_list(price_list)

            if greatest_drop < 0:
                OSMDaily.objects.get_or_create(
                    symbol=asset.symbol,
                    date=day,
                    defaults={
                        "open": daily_open,
                        "close": daily_close,
                        "timestamp": date_to_timestamp(day),
                        "drawdown": daily_drawdown,
                        "daily_low": daily_low,
                        "daily_high": daily_high,
                        "greatest_drop": greatest_drop,
                        "drop_start": drop_start,
                        "drop_end": drop_end,
                    },
                )
