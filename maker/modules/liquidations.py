# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from dateutil import parser
from django.db.models import Q

from maker.models import Liquidation, VaultsLiquidation, VaultsLiquidationHistory


def save_maker_liquidations(backpopulate=False):
    response = requests.get("https://api.makerburn.com/liquidations/all")
    data = response.json()

    latest_liquidation = (
        Liquidation.objects.filter(
            Q(finished=False) | Q(finished=None), protocol="maker"
        )
        .order_by("block_number")
        .first()
    )
    latest_block_number = 0
    if not latest_liquidation:
        try:
            latest_liquidation = Liquidation.objects.filter(protocol="maker").latest()
        except Liquidation.DoesNotExist:
            latest_liquidation = None

    if latest_liquidation:
        latest_block_number = latest_liquidation.block_number

    for item in data:
        if latest_block_number > item["block_number"] and not backpopulate:
            break
        ilk = item["ilk"]
        date_time = item["datetime"]
        timestamp = parser.parse(date_time).timestamp()
        block_number = item["block_number"]
        tx_hash = item["transaction_hash"]
        debt = item["debt"]
        penalty = item["penalty"]
        total_debt = debt + penalty
        tokens = item["tokens"]
        collateral_symbol = ilk.split("-")[0]
        uid = item["id"]

        finished = False
        collateral_seized = None
        collateral_token_price = None
        if item["debt_remaining"] == 0 or item["tokens_remaining"] == 0:
            collateral_seized = tokens - item["tokens_remaining"]
            collateral_token_price = total_debt / collateral_seized
            finished = True

        Liquidation.objects.update_or_create(
            tx_hash=tx_hash,
            uid=uid,
            defaults=dict(
                block_number=block_number,
                timestamp=timestamp,
                datetime=datetime.fromtimestamp(timestamp),
                debt_symbol="DAI",
                debt_token_price=1,
                debt_repaid=debt,
                collateral_symbol=collateral_symbol,
                collateral_token_price=collateral_token_price,
                collateral_seized=collateral_seized,
                protocol="maker",
                finished=finished,
                ilk=ilk,
                penalty=penalty,
            ),
        )


def save_vaults_liquidation_snapshot():
    liquidations = VaultsLiquidation.objects.filter(type__in=["high", "low", "medium"])
    date = datetime.now()
    timestamp = date.timestamp()
    for liquidation in liquidations:
        data = {
            "ilk": liquidation.ilk,
            "drop": liquidation.drop,
            "cr": liquidation.cr,
            "total_debt": liquidation.total_debt,
            "debt": liquidation.debt,
            "current_price": liquidation.current_price,
            "expected_price": liquidation.expected_price,
            "type": liquidation.type,
            "timestamp": timestamp,
            "datetime": date,
        }

        VaultsLiquidationHistory.objects.create(**data)


def get_liquidations_per_drop_data(days_ago, ilk=None):
    timestamp = (datetime.now() - timedelta(days=int(days_ago))).timestamp()
    simulation_timestamp = VaultsLiquidationHistory.objects.all().latest().timestamp
    drops = [5, 10, 15, 20, 30, 40, 50]
    ilk_filter = {}
    if ilk:
        ilk_filter["ilk"] = ilk
    try:
        previous_simulation_timestamp = (
            VaultsLiquidationHistory.objects.filter(
                **ilk_filter, timestamp__lte=timestamp
            )
            .latest()
            .timestamp
        )
    except VaultsLiquidationHistory.DoesNotExist:
        previous_simulation_timestamp = None

    latest_simulation = (
        VaultsLiquidationHistory.objects.filter(
            **ilk_filter, timestamp=simulation_timestamp, drop__in=drops
        )
        .order_by("drop")
        .values("type", "drop", "total_debt")
    )
    if previous_simulation_timestamp:
        try:
            previous_simulation = (
                VaultsLiquidationHistory.objects.filter(
                    **ilk_filter,
                    timestamp=previous_simulation_timestamp,
                    drop__in=drops,
                )
                .order_by("drop")
                .values("type", "drop", "total_debt")
            )
        except VaultsLiquidationHistory.DoesNotExist:
            previous_simulation_timestamp = None

    latest_data = defaultdict(lambda: defaultdict(Decimal))
    previous_data = defaultdict(lambda: defaultdict(Decimal))
    for entry in latest_simulation:
        latest_data[entry["drop"]][entry["type"]] += entry["total_debt"]
    if previous_simulation_timestamp:
        for entry in previous_simulation:
            previous_data[entry["drop"]][entry["type"]] += entry["total_debt"]
    else:
        previous_data = latest_data

    data = []
    for drop, amounts in latest_data.items():
        data.append(
            {
                "drop": drop,
                "high": amounts["high"],
                "high_diff": amounts["high"] - previous_data[drop]["high"],
                "previous_high": previous_data[drop]["high"],
                "medium": amounts["medium"],
                "medium_diff": amounts["medium"] - previous_data[drop]["medium"],
                "previous_medium": previous_data[drop]["medium"],
                "low": amounts["low"],
                "low_diff": amounts["low"] - previous_data[drop]["low"],
                "previous_low": previous_data[drop]["low"],
                "total": amounts["low"] + amounts["medium"] + amounts["high"],
                "total_diff": (amounts["low"] + amounts["medium"] + amounts["high"])
                - (
                    previous_data[drop]["low"]
                    + previous_data[drop]["medium"]
                    + previous_data[drop]["high"]
                ),
                "previous_total": (
                    previous_data[drop]["low"]
                    + previous_data[drop]["medium"]
                    + previous_data[drop]["high"]
                ),
            }
        )

    return data
