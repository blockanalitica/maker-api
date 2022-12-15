# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import date, timedelta

from django.db.models import Sum

from maker.models import LiquidityScore, SlippageDaily, Vault

LIQUIDITY_ASSET_TO_VAULT_INFO_MAP = {
    "WETH": ["ETH-A", "ETH-B", "ETH-C"],
    "MATIC": ["MATIC-A"],
    "LINK": ["LINK-A"],
    "YFI": ["YFI-A"],
    "WBTC": ["WBTC-A", "WBTC-B", "WBTC-C"],
    "WSTETH": ["WSTETH-A", "WSTETH-B"],
}


def _get_slippage(for_date, symbol, debt_exposure):
    if symbol == "WSTETH":
        symbol = "stETH"

    slippage = (
        SlippageDaily.objects.filter(
            date=for_date,
            pair__from_asset__symbol=symbol,
            usd_amount__gt=debt_exposure,
            source="oneinch",
        )
        .order_by("usd_amount")
        .first()
    )

    if not slippage:
        # If we can't get slippage for current debt_exposure, take the slippage for
        # the biggest usd amount we have for current asset
        slippage = (
            SlippageDaily.objects.filter(
                date=for_date, pair__from_asset__symbol=symbol, source="oneinch"
            )
            .order_by("-usd_amount")
            .first()
        )
    return slippage


def calculate_liquidity_score_for_all_assets():
    current_date = date.today()
    for symbol, ilks in LIQUIDITY_ASSET_TO_VAULT_INFO_MAP.items():
        vaults_data = Vault.objects.filter(ilk__in=ilks, is_active=True).aggregate(
            total_debt=Sum("debt"),
        )

        debt_exposure = int(vaults_data["total_debt"] or 0)
        over_time = {}
        for days_ago in range(90):
            for_date = current_date - timedelta(days=days_ago)
            slippage = _get_slippage(for_date, symbol, debt_exposure)
            if not slippage:
                # If we can't get slippage for the date, skip from then on
                break

            liquidity_score = round(100 - abs(slippage.slippage_percent_avg))
            over_time[str(for_date)] = liquidity_score

        # If we don't have liquidation scores, ignore the vault
        if not over_time:
            continue

        LiquidityScore.objects.update_or_create(
            symbol=symbol,
            date=current_date,
            defaults={
                "score": over_time[str(current_date)],
                "debt_exposure": debt_exposure,
                "over_time": over_time,
            },
        )
