# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

import numpy as np
from django.db.models import Avg, F, Sum
from django.db.models.functions import TruncDay, TruncHour

from maker.modules.ilk import get_stats_for_ilk

from ..models import (
    Ilk,
    OverallStat,
    RiskPremium,
    SlippageDaily,
    Vault,
    VaultsLiquidation,
)

log = logging.getLogger(__name__)

MAX_SLIPPAGE = 0.8

JUMP_FREQUENCY_LIST = [1, 2, 3, 4, 5]
KEEPER_PROFIT_LIST = [0.01, 0.025, 0.05, 0.075, 0.1]
JUMP_SEVERITY_LIST = [-0.25, -0.3, -0.35, -0.4, -0.45, -0.5, -0.55, -0.6, -0.65, -0.7]

VAULT_TYPE_TO_VAULT_ASSET_MAPPER = {
    "ETH-A": "WETH",
    "ETH-B": "WETH",
    "ETH-C": "WETH",
    "MANA-A": "MANA",
    "MATIC-A": "MATIC",
    "LINK-A": "LINK",
    "YFI-A": "YFI",
    "UNI-A": "UNI",
    "WBTC-A": "WBTC",
    "WBTC-B": "WBTC",
    "WBTC-C": "WBTC",
    "RENBTC-A": "WBTC",
    "WSTETH-A": "stETH",
    "WSTETH-B": "stETH",
}

VAULT_ASSET_TO_VAULT_TYPE_MAPPER = {
    "WETH": ["ETH-A", "ETH-B", "ETH-C"],
    "MANA": ["MANA-A"],
    "MATIC": ["MATIC-A"],
    "LINK": ["LINK-A"],
    "YFI": ["YFI-A"],
    "UNI": ["UNI-A"],
    "WBTC": ["WBTC-A", "RENBTC-A", "WBTC-B", "WBTC-C"],
    "stETH": ["WSTETH-A", "ETH-A", "ETH-B", "ETH-C", "WSTETH-B"],
}

DEFAULT_SCENARIO_PARAMS = {
    "ETH-A": {
        "jump_severity": -0.5,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "ETH-B": {
        "jump_severity": -0.5,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "ETH-C": {
        "jump_severity": -0.5,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "WSTETH-A": {
        "jump_severity": -0.5,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "WSTETH-B": {
        "jump_severity": -0.5,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "LINK-A": {
        "jump_severity": -0.6,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "MANA-A": {
        "jump_severity": -0.6,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "MATIC-A": {
        "jump_severity": -0.6,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "RENBTC-A": {
        "jump_severity": -0.6,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "UNI-A": {
        "jump_severity": -0.6,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "WBTC-A": {
        "jump_severity": -0.45,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "WBTC-B": {
        "jump_severity": -0.45,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "WBTC-C": {
        "jump_severity": -0.45,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
    "YFI-A": {
        "jump_severity": -0.6,
        "jump_frequency": 2,
        "keeper_profit": 0.05,
    },
}


def _compute_simulated_de(current_de):
    max_steps = 40
    start_ratio = 0.25
    step_ratio = 0.125

    de_ranges = []
    # Round current de to nearest 10k
    current_de_rounded = (
        current_de
        if current_de % 10000 == 0
        else current_de + 10000 - current_de % 10000
    )
    de_ranges.append(current_de_rounded)

    # Add simulated de
    start_simulated_de = int(current_de * start_ratio)
    step_size = int(current_de * step_ratio)
    max_simulated_de = int(start_simulated_de + (step_size * max_steps))

    simualted_ranges = set(
        int(round(value, (-len(str(value)) + 2)))
        for value in range(start_simulated_de, max_simulated_de, step_size)
    )
    de_ranges += list(simualted_ranges)

    return sorted(de_ranges)


def get_share_vaults_protected(ilk, drop):
    drop = abs(drop * 100)
    liquidations = (
        VaultsLiquidation.objects.filter(
            ilk=ilk,
            drop=drop,
            type__in=["high", "medium", "low"],
        )
        .values("total_debt", "type")
        .order_by("type", "-created")
        .distinct("type")
    )
    total_debt = Vault.objects.filter(ilk=ilk, is_active=True).aggregate(
        debt=Sum("debt")
    )["debt"]

    item = {}
    for liquidation in liquidations:
        item[liquidation["type"]] = liquidation["total_debt"]

    weighted_high = item["high"] * Decimal("0.5")
    weighted_medium = item["medium"] * Decimal("0.25")
    weighted_low = item["low"] * Decimal("0.05")

    total_exposure_at_risk = int(weighted_high + weighted_medium + weighted_low)
    share_vaults_protected = float(
        round(abs((total_exposure_at_risk / total_debt) - 1), 2)
    )
    return {
        "share": share_vaults_protected,
        "high": weighted_high,
        "medium": weighted_medium,
        "low": weighted_low,
    }


def compute_scenario_params_psweep(jump_frequency, jump_severity, keeper_profit):
    scenario_params = [
        {
            "scenario_name": "base_case",
            "jump_frequency": jump_frequency,
            "jump_severity": jump_severity,
            "keeper_profit": keeper_profit,
            "share_vaults_protected_drop": jump_severity,
        },
        {
            "scenario_name": "downside_case",
            # move up (jump frequency, jump severity) or down (keeper profit,
            # share vaults protected) in the parameter space list
            "jump_frequency": JUMP_FREQUENCY_LIST[
                min(
                    JUMP_FREQUENCY_LIST.index(jump_frequency) + 1,
                    len(JUMP_FREQUENCY_LIST) - 1,
                )
            ],
            "jump_severity": JUMP_SEVERITY_LIST[
                min(
                    JUMP_SEVERITY_LIST.index(jump_severity) + 2,
                    len(JUMP_SEVERITY_LIST) - 1,
                )
            ],
            "keeper_profit": KEEPER_PROFIT_LIST[
                max(
                    KEEPER_PROFIT_LIST.index(keeper_profit) - 1,
                    0,
                )
            ],
            "cr_distribution": {
                0.15: 2.00,
                0.25: 5.00,
                0.5: 10.00,
                0.75: 15.00,
                1: 15.00,
                1.25: 10.00,
                1.50: 10.00,
                1.75: 5.00,
                2.00: 5.00,
                2.25: 5.00,
                2.50: 5.00,
                2.75: 5.00,
                3.00: 5.00,
                3.25: 3.00,
                3.5: 0.00,
            },
            "share_vaults_protected_drop": JUMP_SEVERITY_LIST[
                min(
                    JUMP_SEVERITY_LIST.index(jump_severity) + 1,
                    4,
                )
            ],
        },
        {
            "scenario_name": "upside_case",
            # move down (jump frequency, jump severity) or up (keeper profit,
            # share vaults protected) in the parameter space list
            "jump_frequency": JUMP_FREQUENCY_LIST[
                max(
                    JUMP_FREQUENCY_LIST.index(jump_frequency) - 1,
                    0,
                )
            ],
            "jump_severity": JUMP_SEVERITY_LIST[
                max(
                    JUMP_SEVERITY_LIST.index(jump_severity) - 2,
                    0,
                )
            ],
            "keeper_profit": KEEPER_PROFIT_LIST[
                min(
                    KEEPER_PROFIT_LIST.index(keeper_profit) + 1,
                    len(KEEPER_PROFIT_LIST) - 1,
                )
            ],
            "cr_distribution": {
                0.15: 0.00,
                0.25: 0.00,
                0.5: 5.00,
                0.75: 5.00,
                1: 5.00,
                1.25: 10.00,
                1.50: 10.00,
                1.75: 10.00,
                2.00: 5.00,
                2.25: 5.00,
                2.50: 10.00,
                2.75: 10.00,
                3.00: 10.00,
                3.25: 10.00,
                3.5: 5.00,
            },
            "share_vaults_protected_drop": JUMP_SEVERITY_LIST[
                max(
                    JUMP_SEVERITY_LIST.index(jump_severity) - 1,
                    0,
                )
            ],
        },
    ]

    return scenario_params


def _get_slippage_for_vault_asset(ilk):
    vault_asset = VAULT_TYPE_TO_VAULT_ASSET_MAPPER[ilk]
    for_date = (
        SlippageDaily.objects.filter(pair__from_asset__symbol=vault_asset)
        .only("date")
        .latest()
        .date
    )
    slippages = (
        SlippageDaily.objects.filter(
            pair__from_asset__symbol=vault_asset,
            date=for_date,
        )
        .values(
            "usd_amount",
            "slippage_list",
        )
        .order_by("usd_amount")
    )

    results = []
    for slippage in slippages:
        slippage_last = slippage["slippage_list"][-1]
        results.append(
            {
                "slippage_percent": abs(slippage_last / 100),
                "usd_amount": int(slippage["usd_amount"]),
            }
        )
    return results


def compute_cr_distribution(liquidation_ratio, ilk):
    buf_range = [
        0.15,
        0.25,
        0.5,
        0.75,
        1.0,
        1.25,
        1.5,
        1.75,
        2.0,
        2.25,
        2.5,
        2.75,
        3.0,
        3.25,
        3.5,
        3.75,
    ]

    cr_limit = 5
    cr_buckets = []
    for buf in buf_range:
        bucket = round(buf + liquidation_ratio, 2)
        if bucket <= cr_limit:
            cr_buckets.append(bucket)

    vaults = list(
        Vault.objects.filter(
            ilk=ilk, is_active=True, collateralization__lte=cr_limit * 100
        )
        .annotate(cr_limit=F("collateralization") / 100)
        .values("collateralization", "debt", "cr_limit")
    )

    total_debt = Decimal("0")
    grouped_debt = {bucket: Decimal("0") for bucket in cr_buckets}
    for vault in vaults:
        cr_bucket = next((x for x in cr_buckets if x > vault["cr_limit"]), None)
        if cr_bucket:
            total_debt += vault["debt"]
            grouped_debt[cr_bucket] += vault["debt"]

    results = []
    for cr_bucket, debt in grouped_debt.items():
        if total_debt == 0:
            total_debt_dai_pdf = 0
        else:
            total_debt_dai_pdf = float(debt / total_debt)
        results.append(
            {"cr_bucket": cr_bucket, "total_debt_dai_pdf": total_debt_dai_pdf}
        )

    return results


def compute_for_vault_type(
    ilk,
    asset_vault_types_dict,
    jump_frequency,
    jump_severity,
    keeper_profit,
):
    log.info(f"Computing simulation results for: {ilk}")
    psweep_scenarios = compute_scenario_params_psweep(
        jump_frequency=jump_frequency,
        jump_severity=jump_severity,
        keeper_profit=keeper_profit,
    )
    current_de = float(asset_vault_types_dict[ilk]["total_debt_dai"])
    slippages = _get_slippage_for_vault_asset(ilk)

    debt_ranges = _compute_simulated_de(current_de)
    max_slippage_usd_amount = slippages[-1]["usd_amount"]

    # compute the simulation results
    simulation_results = []

    # Precompute cr distribution scenarios for each vault type
    cr_scenarios = defaultdict(dict)
    svps = {}
    for asset_vault_type, asset_data in asset_vault_types_dict.items():
        for scenario_params in psweep_scenarios:
            liquidation_ratio = float(asset_data["liquidation_ratio"])
            if scenario_params["scenario_name"] == "base_case":
                # compute the CR distribution
                cr_scenario = compute_cr_distribution(
                    liquidation_ratio,
                    ilk=asset_vault_type,
                )
            else:
                cr_scenario = []
                for buffer, total_debt_dai_pdf in scenario_params[
                    "cr_distribution"
                ].items():
                    cr_scenario.append(
                        {
                            "total_debt_dai_pdf": total_debt_dai_pdf / 100,
                            "cr_bucket": buffer + liquidation_ratio,
                        }
                    )
            cr_scenarios[asset_vault_type][
                scenario_params["scenario_name"]
            ] = cr_scenario

            svp = get_share_vaults_protected(
                asset_vault_type, scenario_params["share_vaults_protected_drop"]
            )

            svps[
                "{}{}".format(
                    asset_vault_type, scenario_params["share_vaults_protected_drop"]
                )
            ] = svp["share"]

    # iterate over debt ceiling simulation values
    for debt_range in debt_ranges:
        scenario_list = []
        # iterate over scenario values
        for scenario_params in psweep_scenarios:
            # compute scenario cr distribution (if base case, use cr distribution)
            # for each vault type
            total_asset_liquidated_debt = 0
            for asset_vault_type, asset_data in asset_vault_types_dict.items():
                liquidation_ratio = float(asset_data["liquidation_ratio"])

                share_vaults_protected = svps[
                    "{}{}".format(
                        asset_vault_type,
                        scenario_params["share_vaults_protected_drop"],
                    )
                ]

                if asset_vault_type != ilk:
                    simulate_de = int(asset_data["total_debt_dai"])
                else:
                    simulate_de = debt_range

                current_de = asset_data["total_debt_dai"]
                if simulate_de > current_de:
                    share_vaults_protected *= current_de / simulate_de

                scenario_cr_dist = cr_scenarios[asset_vault_type][
                    scenario_params["scenario_name"]
                ]
                for cr_scenario in scenario_cr_dist:
                    if (
                        cr_scenario["cr_bucket"]
                        * (1 + scenario_params["jump_severity"])
                        <= liquidation_ratio
                    ):
                        liquidated_debt = round(
                            cr_scenario["total_debt_dai_pdf"]
                            * simulate_de
                            * (1 - share_vaults_protected),
                            2,
                        )

                    else:
                        liquidated_debt = 0.0

                    cr_scenario["liquidated_debt"] = liquidated_debt
                    total_asset_liquidated_debt += liquidated_debt

                if asset_vault_type == ilk:
                    ilk_cr_dist_scenarios = scenario_cr_dist

            # on-chain slippage
            if total_asset_liquidated_debt < max_slippage_usd_amount:
                for slippage in slippages:
                    if slippage["usd_amount"] > total_asset_liquidated_debt:
                        slippage_percent = slippage["slippage_percent"]
                        break

                onchain_slippage = round(float(slippage_percent), 4)
            else:
                onchain_slippage = MAX_SLIPPAGE

            total_loss_bad_debt = 0
            for scenario in ilk_cr_dist_scenarios:
                # liquidated collateral
                liquidated_collateral = round(
                    scenario["liquidated_debt"]
                    * scenario["cr_bucket"]
                    * (1 + scenario_params["jump_severity"]),
                    2,
                )
                # debt repaid
                debt_repaid = liquidated_collateral * (
                    1 - onchain_slippage - scenario_params["keeper_profit"]
                )
                if debt_repaid <= scenario["liquidated_debt"]:
                    debt_repaid = round(debt_repaid, 2)
                else:
                    debt_repaid = scenario["liquidated_debt"]

                # loss (bad debt)
                total_loss_bad_debt += round(
                    debt_repaid - scenario["liquidated_debt"], 3
                )

            # expected loss (risk premium)
            expected_loss = total_loss_bad_debt * scenario_params["jump_frequency"]
            expected_loss_perc = round(
                (expected_loss / debt_range) * 100,
                2,
            )

            scenario_list.append(expected_loss_perc)

        simulation_results.append(
            {
                "simulated_de": debt_range,
                "risk_premium": abs(round(np.mean(scenario_list), 1)),
            }
        )
    return simulation_results


def compute(ilk, jump_frequency, jump_severity, keeper_profit):
    log.info("Got vault info from database: %s", ilk)

    # If vault type doesn't have any vaults, skip it
    if Vault.objects.filter(ilk=ilk, is_active=True).count() == 0:
        return

    vault_asset = VAULT_TYPE_TO_VAULT_ASSET_MAPPER[ilk]

    asset_vault_types = VAULT_ASSET_TO_VAULT_TYPE_MAPPER[vault_asset]
    asset_vault_types_dict = {}
    for asset_vault_type in asset_vault_types:
        log.info("Got asset_vault_type: %s", asset_vault_type)

        vault_data = Vault.objects.filter(
            ilk=asset_vault_type, is_active=True
        ).aggregate(total_debt_dai=Sum("debt"))

        vault = Ilk.objects.only("lr").get(ilk=asset_vault_type)
        asset_vault_types_dict[asset_vault_type] = {
            "total_debt_dai": float(vault_data["total_debt_dai"]),
            "liquidation_ratio": vault.lr,
        }

    vault_type_total_debt_dai = int(asset_vault_types_dict[ilk]["total_debt_dai"])

    results = compute_for_vault_type(
        ilk,
        asset_vault_types_dict,
        jump_frequency=jump_frequency,
        jump_severity=jump_severity,
        keeper_profit=keeper_profit,
    )

    # get max dc at risk premium at more or equal to 10%
    try:
        debt_ceiling = [
            result["simulated_de"] for result in results if result["risk_premium"] >= 10
        ][0]
        debt_ceiling = Decimal(str(debt_ceiling))
    except IndexError:
        debt_ceiling = None

    # get current risk premium based on the current vault type debt
    try:
        risk_premium = [
            result["risk_premium"]
            for result in results
            if result["simulated_de"] >= vault_type_total_debt_dai
        ][0]
        risk_premium = Decimal(str(risk_premium))
    except IndexError:
        risk_premium = None

    svp = get_share_vaults_protected(ilk, jump_severity)

    return {
        "ilk": ilk,
        "data": results,
        "debt_ceiling": debt_ceiling,
        "risk_premium": risk_premium,
        "total_debt_dai": vault_type_total_debt_dai,
        "share_vaults_protected": svp["share"],
        "high_risk_debt": svp["high"],
        "medium_risk_debt": svp["medium"],
        "low_risk_debt": svp["low"],
        "capital_at_risk": int((risk_premium / 100) * vault_type_total_debt_dai),
    }


def compute_all_vault_types():
    for ilk, params in DEFAULT_SCENARIO_PARAMS.items():
        rp = compute(
            ilk,
            params["jump_frequency"],
            params["jump_severity"],
            params["keeper_profit"],
        )

        if not rp:
            log.info("Couldn't calculate risk premium for %s", ilk)
            continue

        stats = get_stats_for_ilk(ilk)
        dt_7 = date.today() - timedelta(days=7)
        dt_30 = date.today() - timedelta(days=30)
        avgs_7d = RiskPremium.objects.filter(datetime__date__gte=dt_7).aggregate(
            debt_ceiling=Avg("debt_ceiling"),
            capital_at_risk=Avg("capital_at_risk"),
            risk_premium=Avg("risk_premium"),
        )
        avgs_30d = RiskPremium.objects.filter(datetime__date__gte=dt_30).aggregate(
            debt_ceiling=Avg("debt_ceiling"),
            capital_at_risk=Avg("capital_at_risk"),
            risk_premium=Avg("risk_premium"),
        )

        RiskPremium.objects.create(
            ilk=ilk,
            timestamp=datetime.now().timestamp(),
            datetime=datetime.now(),
            jump_frequency=params["jump_frequency"],
            jump_severity=params["jump_severity"],
            keeper_profit=params["keeper_profit"],
            data=rp["data"],
            share_vaults_protected=rp["share_vaults_protected"],
            risk_premium=rp["risk_premium"],
            risk_premium_7d_avg=avgs_7d["risk_premium"],
            risk_premium_30d_avg=avgs_30d["risk_premium"],
            debt_ceiling=rp["debt_ceiling"],
            debt_ceiling_7d_avg=avgs_7d["debt_ceiling"],
            debt_ceiling_30d_avg=avgs_30d["debt_ceiling"],
            total_debt_dai=rp["total_debt_dai"],
            capital_at_risk=rp["capital_at_risk"],
            capital_at_risk_7d_avg=avgs_7d["capital_at_risk"],
            capital_at_risk_30d_avg=avgs_30d["capital_at_risk"],
            high_risk_debt=rp["high_risk_debt"],
            medium_risk_debt=rp["medium_risk_debt"],
            low_risk_debt=rp["low_risk_debt"],
            collateralization_ratio=stats["weighted_collateralization_ratio"],
        )
        Ilk.objects.filter(ilk=ilk).update(
            risk_premium=rp["risk_premium"], capital_at_risk=rp["capital_at_risk"]
        )


def get_capital_at_risk_history_ilks(days_ago=30):
    dt = datetime.now() - timedelta(days=days_ago)
    risk_simulations = (
        RiskPremium.objects.filter(datetime__gte=dt)
        .annotate(dt=TruncHour("datetime"))
        .values(
            "ilk", "datetime", "risk_premium", "total_debt_dai", "capital_at_risk", "dt"
        )
    )
    return risk_simulations


def get_risky_debt_history(days_ago=30):
    dt = datetime.now() - timedelta(days=days_ago)
    overall_stats = (
        OverallStat.objects.filter(datetime__gte=dt)
        .annotate(
            dt=TruncHour("datetime"),
            risky_debt=(F("capital_at_risk") / F("total_risky_debt") * 100),
        )
        .values("dt", "risky_debt", "capital_at_risk", "total_risky_debt")
    )

    return overall_stats


def get_capital_at_risk_history_overall(days_ago=30):
    dt = datetime.now() - timedelta(days=days_ago)
    return (
        OverallStat.objects.filter(datetime__gte=dt, capital_at_risk__isnull=False)
        .annotate(dt=TruncDay("datetime"))
        .values(
            "datetime",
            "capital_at_risk",
            "capital_at_risk_7d_avg",
            "capital_at_risk_30d_avg",
            "surplus_buffer",
            "dt",
        )
        .order_by("dt", "-datetime")
        .distinct("dt")
    )


def get_capital_at_risk_history_for_ilk(ilk, days_ago=30):
    dt = datetime.now() - timedelta(days=days_ago)
    risk_simulations = (
        RiskPremium.objects.filter(ilk=ilk, datetime__gte=dt)
        .values(
            "ilk",
            "datetime",
            "risk_premium",
            "total_debt_dai",
            "capital_at_risk",
            "capital_at_risk_30d_avg",
            "capital_at_risk_7d_avg",
            "risk_premium_30d_avg",
            "risk_premium_7d_avg",
            "share_vaults_protected",
            "collateralization_ratio",
        )
        .order_by("datetime")
    )
    return risk_simulations


def get_capital_at_risk_history_for_ilk_score(ilk, days_ago=30):
    dt = datetime.now() - timedelta(days=days_ago)
    risk_simulations = (
        RiskPremium.objects.filter(
            ilk=ilk, datetime__gte=dt, high_risk_debt__isnull=False
        )
        .values(
            "datetime",
            "high_risk_debt",
            "medium_risk_debt",
            "low_risk_debt",
        )
        .order_by("datetime")
    )
    return risk_simulations


def get_capital_at_risk_for_ilk(ilk, days_ago=1):
    rp = RiskPremium.objects.filter(ilk=ilk).latest()

    data = {
        "risk_premium": rp.risk_premium,
        "capital_at_risk": rp.capital_at_risk,
        "total_debt": rp.total_debt_dai,
        "capital_at_risk_avg": rp.capital_at_risk_30d_avg,
        "risk_premium_avg": rp.risk_premium_30d_avg,
    }

    if days_ago:
        start_date = datetime.now() - timedelta(days=days_ago)
        old_rp = RiskPremium.objects.filter(ilk=ilk, datetime__lte=start_date).latest()
        changes = {
            "risk_premium": old_rp.risk_premium,
            "capital_at_risk": old_rp.capital_at_risk,
            "total_debt": old_rp.total_debt_dai,
            "capital_at_risk_avg": old_rp.capital_at_risk_30d_avg,
            "risk_premium_avg": old_rp.risk_premium_30d_avg,
        }
        data["change"] = changes

    return data
