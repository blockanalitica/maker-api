# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError
from django_bulk_load import bulk_insert_models
from web3 import Web3

from maker.constants import CHAINLINK_PROXY_ADDRESSES
from maker.models import Asset, MarketPrice, TokenPriceHistory
from maker.sources.llama import fetch_current_price
from maker.utils.blockchain.chain import Blockchain
from maker.utils.utils import chunks

log = logging.getLogger(__name__)


def sync_chainlink_rounds():
    w3 = Blockchain(node=settings.ETH_NODE_MAKER)
    save_eth_rounds(chain=w3)
    save_exceptions_rounds(chain=w3)
    save_remaining_rounds(chain=w3)


def save_eth_rounds(chain=None):
    w3 = Blockchain(_web3=chain)
    token = Asset.objects.get(underlying_symbol="ETH")
    try:
        saved_round = int(
            TokenPriceHistory.objects.filter(underlying_symbol="ETH").latest().round_id
        )
    except TokenPriceHistory.DoesNotExist:
        populate_eth_price_history(chain=w3)
        return
    latest_phase = get_token_phase_id(token.address, chain=w3)
    decimals = get_token_decimals(token.address, chain=w3)
    aggregator = get_token_aggregator(token.address, latest_phase["id"], chain=w3)
    latest_aggregator_round = get_latest_round(aggregator["address"])
    latest_proxy_round = latest_phase["id"] << 64 | latest_aggregator_round
    if saved_round == latest_proxy_round:
        return
    earliest_proxy_round = latest_phase["id"] << 64 | 1
    all_rounds = [*range(earliest_proxy_round, latest_proxy_round + 1, 1)]
    if saved_round in all_rounds:
        all_rounds = all_rounds[all_rounds.index(saved_round) + 1 :]
    else:
        previous_aggregator = get_token_aggregator(
            token.address, latest_phase["id"] - 1, chain=w3
        )
        previous_aggregator_round = get_latest_round(previous_aggregator["address"])
        end_proxy_round = (latest_phase["id"] - 1) << 64 | previous_aggregator_round
        start_proxy_round = (latest_phase["id"] - 1) << 64 | 1
        previous_rounds = [*range(start_proxy_round, end_proxy_round + 1, 1)]
        previous_rounds = previous_rounds[previous_rounds.index(saved_round) + 1 :]
        all_rounds = previous_rounds + all_rounds
    for rounds in chunks(all_rounds, 5000):
        rounds_data = get_price_history(token.address, rounds, chain=w3)
        for round_id, data in rounds_data.items():

            TokenPriceHistory.objects.get_or_create(
                underlying_address=token.address,
                round_id=str(round_id),
                timestamp=data[3],
                defaults={
                    "underlying_symbol": token.underlying_symbol,
                    "price": data[1] / 10 ** decimals["number"],
                },
            )


def save_exceptions_rounds(chain=None):
    w3 = Blockchain(_web3=chain)
    tokens = Asset.objects.filter(
        underlying_symbol__in=["ENS", "USDP", "sUSD", "UST", "MATIC", "CVX", "LUSD"]
    )
    for token in tokens:
        try:
            saved_round = int(
                TokenPriceHistory.objects.filter(
                    underlying_symbol=token.underlying_symbol
                )
                .latest()
                .round_id
            )
        except TokenPriceHistory.DoesNotExist:
            backpopulate_exception_tokens_history(token, chain=w3)
            continue
        latest_phase = get_token_phase_id(token.address, chain=w3)
        decimals = get_token_decimals(token.address, chain=w3)
        aggregator = get_token_aggregator(token.address, latest_phase["id"], chain=w3)

        latest_aggregator_round = get_latest_round(aggregator["address"])
        latest_proxy_round = latest_phase["id"] << 64 | latest_aggregator_round
        if saved_round == latest_proxy_round:
            continue
        earliest_proxy_round = latest_phase["id"] << 64 | 1
        all_rounds = [*range(earliest_proxy_round, latest_proxy_round + 1, 1)]
        if saved_round in all_rounds:
            all_rounds = all_rounds[all_rounds.index(saved_round) + 1 :]
        else:
            previous_aggregator = get_token_aggregator(
                token.address, latest_phase["id"] - 1, chain=w3
            )
            previous_aggregator_round = get_latest_round(previous_aggregator["address"])
            end_proxy_round = (latest_phase["id"] - 1) << 64 | previous_aggregator_round
            start_proxy_round = (latest_phase["id"] - 1) << 64 | 1
            previous_rounds = [*range(start_proxy_round, end_proxy_round + 1, 1)]
            previous_rounds = previous_rounds[previous_rounds.index(saved_round) + 1 :]
            all_rounds = previous_rounds + all_rounds
        for rounds in chunks(all_rounds, 5000):
            rounds_data = get_price_history(token.address, rounds, chain=w3)
            for round_id, data in rounds_data.items():

                TokenPriceHistory.objects.get_or_create(
                    underlying_address=token.address,
                    round_id=str(round_id),
                    timestamp=data[3],
                    defaults={
                        "underlying_symbol": token.underlying_symbol,
                        "price": data[1] / 10 ** decimals["number"],
                    },
                )


def save_remaining_rounds(chain=None):
    w3 = Blockchain(_web3=chain)
    tokens = Asset.objects.all().exclude(
        underlying_symbol__in=[
            "ETH",
            "ENS",
            "sUSD",
            "USDP",
            "UST",
            "MATIC",
            "CVX",
            "LUSD",
        ]
    )
    for token in tokens:
        if token.address not in CHAINLINK_PROXY_ADDRESSES:
            continue
        underlying_address = token.address
        if underlying_address == "0xeb4c2781e4eba804ce9a9803c67d0893436bb27d":
            underlying_address = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"
        try:
            saved_round = int(
                TokenPriceHistory.objects.filter(
                    underlying_symbol=token.underlying_symbol
                )
                .latest()
                .round_id
            )
        except TokenPriceHistory.DoesNotExist:
            backpopulate_remaining_tokens_history(token, chain=w3)
            continue
        latest_phase = get_token_phase_id(underlying_address, chain=w3)
        decimals = get_token_decimals(underlying_address, chain=w3)
        aggregator = get_token_aggregator(
            underlying_address, latest_phase["id"], chain=w3
        )

        latest_aggregator_round = get_latest_round(aggregator["address"])
        latest_proxy_round = latest_phase["id"] << 64 | latest_aggregator_round
        if saved_round == latest_proxy_round:
            all_rounds = [saved_round]
        else:
            earliest_proxy_round = latest_phase["id"] << 64 | 1
            all_rounds = [*range(earliest_proxy_round, latest_proxy_round + 1, 1)]
            if saved_round in all_rounds:
                all_rounds = all_rounds[all_rounds.index(saved_round) + 1 :]
            else:
                previous_aggregator = get_token_aggregator(
                    underlying_address, latest_phase["id"] - 1, chain=w3
                )
                previous_aggregator_round = get_latest_round(
                    previous_aggregator["address"]
                )
                end_proxy_round = (
                    latest_phase["id"] - 1
                ) << 64 | previous_aggregator_round
                start_proxy_round = (latest_phase["id"] - 1) << 64 | 1
                previous_rounds = [*range(start_proxy_round, end_proxy_round + 1, 1)]
                previous_rounds = previous_rounds[
                    previous_rounds.index(saved_round) + 1 :
                ]
                all_rounds = previous_rounds + all_rounds
        for rounds in chunks(all_rounds, 5000):
            rounds_data = get_price_history(underlying_address, rounds, chain=w3)
            for round_id, data in rounds_data.items():
                price_in_eth = data[1] / 10 ** decimals["number"]
                eth_price = (
                    TokenPriceHistory.objects.filter(underlying_symbol="ETH")
                    .latest()
                    .price
                )
                price_in_usd = Decimal(str(price_in_eth)) * eth_price

                TokenPriceHistory.objects.update_or_create(
                    underlying_address=token.address,
                    round_id=str(round_id),
                    timestamp=data[3],
                    defaults={
                        "underlying_symbol": token.underlying_symbol,
                        "price": price_in_usd,
                    },
                )


def backpopulate_exception_tokens_history(token, chain=None):
    w3 = Blockchain(_web3=chain)
    bulk_create = []
    latest_phase = get_token_phase_id(token.address, chain=w3)
    decimals = get_token_decimals(token.address, chain=w3)
    aggregator_addresses = get_token_aggregators(
        token.address, latest_phase["id"], chain=w3
    )

    for phase, phase_aggregator in aggregator_addresses.items():
        latest_aggregator_round = get_latest_round(phase_aggregator)
        latest_proxy_round = phase << 64 | latest_aggregator_round
        earliest_proxy_round = phase << 64 | 1
        all_rounds = [*range(earliest_proxy_round, latest_proxy_round + 1, 1)]
        for rounds in chunks(all_rounds, 5000):
            rounds_data = get_price_history(token.address, rounds, chain=w3)
            for round_id, data in rounds_data.items():
                bulk_create.append(
                    TokenPriceHistory(
                        underlying_symbol=token.underlying_symbol,
                        price=data[1] / 10 ** decimals["number"],
                        timestamp=data[3],
                        round_id=str(round_id),
                        underlying_address=token.address,
                    )
                )
    bulk_insert_models(bulk_create, ignore_conflicts=True)


def backpopulate_remaining_tokens_history(token, chain=None):
    w3 = Blockchain(_web3=chain)
    bulk_create = []
    underlying_address = token.address
    if underlying_address == "0xeb4c2781e4eba804ce9a9803c67d0893436bb27d":
        underlying_address = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"
    phase = get_token_phase_id(underlying_address, chain=w3)
    decimals = get_token_decimals(underlying_address, chain=w3)
    aggregator_addresses = get_token_aggregators(
        underlying_address, phase["id"], chain=w3
    )

    for phase_id, phase_aggregator in aggregator_addresses.items():
        latest_aggregator_round = get_latest_round(phase_aggregator)
        latest_proxy_round = phase_id << 64 | latest_aggregator_round
        earliest_proxy_round = phase_id << 64 | 1
        if phase_aggregator == list(aggregator_addresses.values())[0]:
            earliest_proxy_round = phase_id << 64 | 40
        all_rounds = [*range(earliest_proxy_round, latest_proxy_round + 1, 1)]
        for rounds in chunks(all_rounds, 5000):
            rounds_data = get_price_history(underlying_address, rounds, chain=w3)
            for round_id, data in rounds_data.items():
                price_in_eth = data[1] / 10 ** decimals["number"]
                eth_price = (
                    TokenPriceHistory.objects.filter(
                        underlying_symbol="ETH", timestamp__lte=data[3]
                    )
                    .latest()
                    .price
                )
                price_in_usd = Decimal(str(price_in_eth)) * eth_price
                bulk_create.append(
                    TokenPriceHistory(
                        underlying_symbol=token.underlying_symbol,
                        price=price_in_usd,
                        timestamp=data[3],
                        round_id=str(round_id),
                        underlying_address=token.address,
                    )
                )
    bulk_insert_models(bulk_create, ignore_conflicts=True)


def populate_eth_price_history(chain=None):
    w3 = Blockchain(_web3=chain)
    bulk_create = []
    token = Asset.objects.get(underlying_symbol="ETH")
    latest_phase = get_token_phase_id(token.address, chain=w3)
    decimals = get_token_decimals(token.address, chain=w3)
    aggregator_addresses = get_token_aggregators(
        token.address, latest_phase["id"], chain=w3
    )
    for phase, phase_aggregator in aggregator_addresses.items():
        latest_aggregator_round = get_latest_round(phase_aggregator)
        latest_proxy_round = phase << 64 | latest_aggregator_round
        earliest_proxy_round = phase << 64 | 1
        all_rounds = [*range(earliest_proxy_round, latest_proxy_round + 1, 1)]
        for rounds in chunks(all_rounds, 5000):
            rounds_data = get_price_history(token.address, rounds, chain=w3)
            for round_id, data in rounds_data.items():
                bulk_create.append(
                    TokenPriceHistory(
                        underlying_symbol=token.underlying_symbol,
                        price=data[1] / 10 ** decimals["number"],
                        timestamp=data[3],
                        round_id=str(round_id),
                        underlying_address=token.address,
                    )
                )
    bulk_insert_models(bulk_create, ignore_conflicts=True)


def get_token_decimals(underlying_address, chain=None):
    w3 = Blockchain(_web3=chain)
    token_proxy_address = CHAINLINK_PROXY_ADDRESSES[underlying_address]
    call = [
        (
            token_proxy_address,
            [
                "decimals()(uint8)",
            ],
            ["number", None],
        )
    ]

    data = w3.call_multicall(call)

    return data


def get_price_history(underlying_address, rounds, chain=None):
    w3 = Blockchain(_web3=chain)
    token_calls = []
    for round in rounds:
        token_proxy_address = CHAINLINK_PROXY_ADDRESSES[underlying_address]
        token_calls.append(
            (
                token_proxy_address,
                ["getRoundData(uint80)((uint80,int256,uint256,uint256,uint80))", round],
                [round, None],
            )
        )

    data = w3.call_multicall(token_calls)
    return data


def get_latest_round(phase_aggregator, chain=None):
    w3 = Blockchain(_web3=chain)
    checksum = Web3.toChecksumAddress(phase_aggregator)
    contract = w3.get_contract(checksum, abi_type="chainlink_aggregator")
    latest_round = contract.caller.latestRound()

    return latest_round


def get_token_phase_id(underlying_address, chain=None):
    w3 = Blockchain(_web3=chain)
    token_proxy_address = CHAINLINK_PROXY_ADDRESSES[underlying_address]
    call = [
        (
            token_proxy_address,
            [
                "phaseId()(uint16)",
            ],
            ["id", None],
        )
    ]

    data = w3.call_multicall(call)

    return data


def get_token_aggregator(underlying_address, phase, chain=None):
    w3 = Blockchain(_web3=chain)
    token_proxy_address = CHAINLINK_PROXY_ADDRESSES[underlying_address]

    call = [
        (
            token_proxy_address,
            ["phaseAggregators(uint16)(address)", phase],
            ["address", None],
        )
    ]

    data = w3.call_multicall(call)

    return data


def get_token_aggregators(underlying_address, phase, chain=None):
    w3 = Blockchain(_web3=chain)
    token_calls = []
    starting_phase = 1
    if phase >= 4:
        starting_phase = 3
    if (
        underlying_address == "0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e"
        or underlying_address == "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9"
        or underlying_address == "0xc00e94cb662c3520282e6f5717214004a7f26888"
    ):
        starting_phase = 2
    token_proxy_address = CHAINLINK_PROXY_ADDRESSES[underlying_address]
    for phase in range(starting_phase, phase + 1, 1):
        token_calls.append(
            (
                token_proxy_address,
                ["phaseAggregators(uint16)(address)", phase],
                [phase, None],
            )
        )

    data = w3.call_multicall(token_calls)

    return data


def save_market_prices():
    markets = Asset.objects.values("symbol", "address")

    coins = []
    for market in markets:
        coins.append("ethereum:{}".format(market["address"]))

    # Deduplicate coins
    coins = list(set(coins))
    data = fetch_current_price(coins)
    for coin in coins:
        info = data[coin]
        symbol = info["symbol"].upper()
        if symbol == "WETH":
            symbol = "ETH"
        try:
            MarketPrice.objects.create(
                symbol=symbol,
                price=info["price"],
                timestamp=info["timestamp"],
                datetime=datetime.fromtimestamp(info["timestamp"]),
            )
            Asset.objects.filter(symbol=info["symbol"]).update(price=info["price"])
        except IntegrityError:
            log.debug(
                "MarketPrice for %s and timestamp %s already exists",
                info["symbol"],
                info["timestamp"],
            )
