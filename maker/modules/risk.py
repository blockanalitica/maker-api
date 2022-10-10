# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum

from maker.utils.blockchain.chain import Blockchain

from ..constants import MCD_VAT_CONTRACT_ADDRESS, MCD_VOW_CONTRACT_ADDRESS
from ..models import (
    Ilk,
    OverallStat,
    RiskPremium,
    SurplusBuffer,
    Vault,
    VaultsLiquidation,
)


def get_surplus_buffer():
    chain = Blockchain()
    contract = chain.get_contract(MCD_VAT_CONTRACT_ADDRESS)
    dai = contract.caller.dai(MCD_VOW_CONTRACT_ADDRESS) / 10**45
    sin = contract.caller.sin(MCD_VOW_CONTRACT_ADDRESS) / 10**45
    return dai - sin


def save_surplus_buffer():
    dt = datetime.now()
    timestamp = dt.timestamp()
    amount = get_surplus_buffer()
    SurplusBuffer.objects.create(amount=amount, datetime=dt, timestamp=timestamp)


def get_liquidation_curve_for_all(type="total"):

    data = defaultdict(lambda: defaultdict(Decimal))
    liquidations = (
        VaultsLiquidation.objects.all()
        .exclude(type="all")
        .order_by("drop")
        .values("drop", "total_debt", "type", "debt")
    )

    for liquidation in liquidations:
        if type == "total":
            data[liquidation["drop"]][liquidation["type"]] += liquidation["total_debt"]
        elif type == "bucket":
            data[liquidation["drop"]][liquidation["type"]] += liquidation["debt"]

    result = []

    for drop, values in data.items():
        for type, total_debt in values.items():
            result.append(
                {
                    "protection_score": type,
                    "debt": total_debt,
                    "drop": drop,
                }
            )
    return result


def get_overall_stats(days_ago=None):
    total_dai_debt = Ilk.objects.filter(is_active=True).aggregate(Sum("dai_debt"))[
        "dai_debt__sum"
    ]
    total_risky_debt = Ilk.objects.filter(
        is_active=True, type__in=["lp", "asset"], is_stable=False
    ).aggregate(Sum("dai_debt"))["dai_debt__sum"]

    total_stable_debt = Ilk.objects.filter(is_active=True, is_stable=True).aggregate(
        Sum("dai_debt")
    )["dai_debt__sum"]
    vault_count = Vault.objects.filter(is_active=True).count()
    risk_premium_ids = (
        RiskPremium.objects.all()
        .order_by("ilk", "-timestamp")
        .distinct("ilk")
        .values_list("id", flat=True)
    )
    risk_data = RiskPremium.objects.filter(id__in=risk_premium_ids).aggregate(
        high_risk=Sum("high_risk_debt"),
        medium_risk=Sum("medium_risk_debt"),
        low_risk=Sum("low_risk_debt"),
        capital_at_risk=Sum("capital_at_risk"),
        capital_at_risk_7d_avg=Sum("capital_at_risk_7d_avg"),
        capital_at_risk_30d_avg=Sum("capital_at_risk_30d_avg"),
    )
    surplus_buffer = SurplusBuffer.objects.latest().amount

    data = {
        "total_debt": total_dai_debt,
        "total_risky_debt": total_risky_debt,
        "total_stable_debt": total_stable_debt,
        "surplus_buffer": surplus_buffer,
        "vault_count": vault_count,
        "high_risk": risk_data["high_risk"],
        "medium_risk": risk_data["medium_risk"],
        "low_risk": risk_data["low_risk"],
        "capital_at_risk": risk_data["capital_at_risk"],
        "capital_at_risk_7d_avg": risk_data["capital_at_risk_7d_avg"],
        "capital_at_risk_30d_avg": risk_data["capital_at_risk_30d_avg"],
    }

    if days_ago:
        dt = datetime.now() - timedelta(days=days_ago)
        stats = None
        try:
            stats = OverallStat.objects.filter(
                datetime__lte=dt, total_debt__isnull=False
            ).latest()
        except OverallStat.DoesNotExist:
            pass

        change = {}
        if stats:
            change = {
                "total_debt": stats.total_debt,
                "total_risky_debt": stats.total_risky_debt,
                "total_stable_debt": stats.total_stable_debt,
                "surplus_buffer": stats.surplus_buffer,
                "capital_at_risk": stats.capital_at_risk,
                "capital_at_risk_7d_avg": stats.capital_at_risk_7d_avg,
                "capital_at_risk_30d_avg": stats.capital_at_risk_30d_avg,
                "total_debt_diff": round(total_dai_debt - stats.total_debt),
                "total_risky_debt_diff": round(
                    total_risky_debt - stats.total_risky_debt
                ),
                "total_stable_debt_diff": round(
                    total_stable_debt - stats.total_stable_debt
                ),
                "surplus_buffer_diff": round(surplus_buffer - stats.surplus_buffer),
                "capital_at_risk_diff": round(
                    risk_data["capital_at_risk"] - stats.capital_at_risk
                ),
                "capital_at_risk_7d_avg_diff": round(
                    risk_data["capital_at_risk_7d_avg"] - stats.capital_at_risk_7d_avg
                ),
                "capital_at_risk_30d_avg_diff": round(
                    risk_data["capital_at_risk_30d_avg"] - stats.capital_at_risk_30d_avg
                ),
            }
            if stats.vault_count:
                change["vault_count"] = stats.vault_count
                change["vault_count_diff"] = vault_count - stats.vault_count
        data["change"] = change

    data.update(risk_data)
    return data


def save_overall_stats():
    data = get_overall_stats()
    OverallStat.objects.create(
        datetime=datetime.now(),
        timestamp=datetime.now().timestamp(),
        total_debt=data["total_debt"],
        total_risky_debt=data["total_risky_debt"],
        total_stable_debt=data["total_stable_debt"],
        surplus_buffer=data["surplus_buffer"],
        capital_at_risk=data["capital_at_risk"],
        capital_at_risk_7d_avg=data["capital_at_risk_7d_avg"],
        capital_at_risk_30d_avg=data["capital_at_risk_30d_avg"],
        high_risk=data["high_risk"],
        medium_risk=data["medium_risk"],
        low_risk=data["low_risk"],
        vault_count=data["vault_count"],
    )
