# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from django.db.models import F

from maker.models import OSM, Ilk, MarketPrice, Vault
from maker.modules.osm import get_osm_and_medianizer

log = logging.getLogger(__name__)


def get_vaults_at_risk():
    symbols = set()
    category_debt = {"high": 0, "medium": 0, "low": 0}
    total_debt = 0
    aggregate_data = {}
    vaults_at_risk = (
        Vault.objects.filter(is_at_risk=True, is_active=True)
        .exclude(ilk__in=["GUNIV3DAIUSDC2-A", "UNIV2DAIUSDC-A", "GUNIV3DAIUSDC1-A"])
        .values(
            "uid",
            "ilk",
            "collateral_symbol",
            "owner_address",
            "collateral",
            "debt",
            "collateralization",
            "liquidation_price",
            "protection_score",
            "last_activity",
            "owner_ens",
            "owner_name",
            "protection_service",
        )
    )

    for vault in vaults_at_risk:
        symbols.add(vault["collateral_symbol"])
        if vault["protection_score"]:
            category_debt[vault["protection_score"]] += vault["debt"]
        total_debt += vault["debt"]
    aggregate_data["total_debt"] = total_debt
    aggregate_data["count"] = len(vaults_at_risk)
    aggregate_data.update(category_debt)

    osm_prices = []
    for symbol in symbols:
        try:
            data = get_osm_and_medianizer(symbol)
            osm_prices.append(data)
        except Exception:
            log.exception("Error fetching OSM for symbol %s", symbol)

    data = {
        "aggregate_data": aggregate_data,
        "vaults": vaults_at_risk,
        "osm_prices": osm_prices,
    }
    return data


def get_vaults_at_risk_market():
    symbols = set()
    category_debt = {"high": 0, "medium": 0, "low": 0}
    total_debt = 0
    aggregate_data = {}
    vaults_at_risk = Vault.objects.filter(
        is_at_risk_market=True, is_active=True
    ).values(
        "uid",
        "ilk",
        "collateral_symbol",
        "owner_address",
        "collateral",
        "debt",
        "collateralization",
        "liquidation_price",
        "protection_score",
        "last_activity",
        "owner_ens",
        "owner_name",
        "protection_service",
    )

    for vault in vaults_at_risk:
        symbols.add(vault["collateral_symbol"])
        if vault["protection_score"]:
            category_debt[vault["protection_score"]] += vault["debt"]
        total_debt += vault["debt"]
    aggregate_data["total_debt"] = total_debt
    aggregate_data["count"] = len(vaults_at_risk)
    aggregate_data.update(category_debt)

    market_prices = []
    for symbol in symbols:
        try:
            market_price = MarketPrice.objects.filter(symbol=symbol).latest()
            data = {
                "symbol": symbol,
                "price": market_price.price,
                "datetime": market_price.datetime,
            }
            market_prices.append(data)
        except Exception:
            log.exception("Error fetching OSM for symbol %s", symbol)

    data = {
        "aggregate_data": aggregate_data,
        "vaults": vaults_at_risk,
        "market_prices": market_prices,
    }
    return data


def refresh_vaults_at_risk(symbol):
    osm = OSM.objects.latest_for_asset(symbol=symbol)
    price = min(osm.current_price, osm.next_price)

    for ilk in Ilk.objects.filter(collateral=symbol):
        Vault.objects.filter(ilk=ilk.ilk, is_active=True).update(
            liquidation_price=(F("debt") * ilk.lr) / F("collateral")
        )
        Vault.objects.filter(
            ilk=ilk.ilk, is_active=True, liquidation_price__gte=price
        ).update(is_at_risk=True)


def refresh_market_risk_for_vaults(symbol):
    try:
        market_price = MarketPrice.objects.filter(symbol=symbol).latest().price
    except MarketPrice.DoesNotExist:
        return
    for ilk in Ilk.objects.filter(collateral=symbol):
        Vault.objects.filter(ilk=ilk.ilk, is_active=True).update(
            mkt_price=market_price, is_at_risk_market=False
        )
        Vault.objects.filter(
            ilk=ilk.ilk, is_active=True, liquidation_price__gte=market_price
        ).update(is_at_risk_market=True)
