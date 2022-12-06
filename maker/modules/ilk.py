# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from django.db.models import Avg, Count, F, Sum
from django.db.models.functions import TruncDay
from django.db.models.query_utils import Q

from maker.models import Ilk, IlkHistoricStats, RiskPremium, Vault, VaultsLiquidation
from maker.utils.utils import get_date_timestamp_days_ago


def get_stats_for_ilk(ilk, days_ago=None):
    vaults_data = Vault.objects.filter(ilk=ilk, is_active=True).values(
        "debt", "collateral", "collateralization"
    )
    if len(vaults_data) == 0:
        return {
            "total_debt": 0,
            "total_locked": 0,
            "vaults_count": 0,
            "weighted_collateralization_ratio": 0,
            "change": {},
            "capital_at_risk": 0,
            "risk_premium": 0,
        }

    aggregate_data = Vault.objects.filter(ilk=ilk, is_active=True).aggregate(
        total_debt=Sum("debt"), total_locked=Sum("collateral")
    )

    total_debt = aggregate_data["total_debt"]
    total_locked = aggregate_data["total_locked"]

    weighted_collateralization_ratio = sum(
        vault["debt"] / total_debt * vault["collateralization"]
        for vault in vaults_data
        if vault["collateralization"]
    )
    try:
        rp = RiskPremium.objects.filter(ilk=ilk).latest()
        risk_premium = rp.risk_premium
        capital_at_risk = rp.capital_at_risk
    except RiskPremium.DoesNotExist:
        risk_premium = 0
        capital_at_risk = 0
    change = {}
    if days_ago:
        dt = datetime.now() - timedelta(days=days_ago)
        stats = (
            IlkHistoricStats.objects.filter(ilk=ilk, datetime__lte=dt)
            .order_by("-timestamp")
            .first()
        )

        if stats:
            change = {
                "total_debt": stats.total_debt,
                "total_locked": stats.total_locked,
                "vaults_count": stats.vaults_count,
                "weighted_collateralization_ratio": stats.weighted_collateralization_ratio,
                "total_debt_diff": round(total_debt - stats.total_debt),
                "total_locked_diff": round(total_locked - stats.total_locked),
                "vaults_count_diff": len(vaults_data) - stats.vaults_count,
                "weighted_collateralization_ratio_diff": round(
                    weighted_collateralization_ratio
                    - stats.weighted_collateralization_ratio,
                    2,
                ),
                "capital_at_risk": stats.capital_at_risk,
                "capital_at_risk_diff": capital_at_risk - (stats.capital_at_risk or 0),
                "risk_premium": stats.risk_premium,
                "risk_premium_diff": risk_premium - (stats.risk_premium or 0),
            }

    return {
        "total_debt": total_debt,
        "total_locked": total_locked,
        "vaults_count": len(vaults_data),
        "weighted_collateralization_ratio": weighted_collateralization_ratio,
        "change": change,
        "capital_at_risk": capital_at_risk,
        "risk_premium": risk_premium,
    }


def get_historic_stats_for_ilk(ilk, stat_type, days_ago):
    ilk_obj = Ilk.objects.get(ilk=ilk)
    dt = datetime.utcnow() - timedelta(days=days_ago)
    org_stats_type = stat_type
    if org_stats_type == "cr_lr":
        stat_type = "weighted_collateralization_ratio"

    filters = {f"{stat_type}__isnull": False}
    data = (
        IlkHistoricStats.objects.filter(ilk=ilk, datetime__gte=dt, **filters)
        .values("datetime", stat_type)
        .order_by("datetime")
    )
    for item in data:
        if org_stats_type == "cr_lr":
            item["value"] = (item[stat_type] / ilk_obj.lr) / 100
        else:
            item["value"] = item[stat_type]
    return data


def get_capital_at_risk_historic_stats_for_ilk(ilk, days_ago):
    dt = datetime.utcnow() - timedelta(days=days_ago)

    data = (
        IlkHistoricStats.objects.filter(
            ilk=ilk, datetime__gte=dt, capital_at_risk__isnull=False
        )
        .annotate(dt=TruncDay("datetime"))
        .values(
            "timestamp",
            "datetime",
            "capital_at_risk",
            "capital_at_risk_7d_avg",
            "capital_at_risk_30d_avg",
            "dt",
        )
        .order_by("dt", "-datetime")
        .distinct("dt")
    )
    return data


def get_risk_premium_historic_stats_for_ilk(ilk, days_ago):
    dt = datetime.utcnow() - timedelta(days=days_ago)

    data = (
        IlkHistoricStats.objects.filter(
            ilk=ilk, datetime__gte=dt, capital_at_risk__isnull=False
        )
        .annotate(dt=TruncDay("datetime"))
        .values(
            "timestamp",
            "datetime",
            "risk_premium",
            "risk_premium_7d_avg",
            "risk_premium_30d_avg",
            "dt",
        )
        .order_by("dt", "-datetime")
        .distinct("dt")
    )
    return data


def save_stats_for_vault(ilk):
    stats = get_stats_for_ilk(ilk)
    if not stats:
        return

    protected = Vault.objects.filter(protection_service__isnull=False).aggregate(
        debt=Sum("debt"), count=Count("id")
    )
    protected_count = protected["count"] or 0
    protected_debt = protected["debt"] or 0

    if stats["total_debt"] == 0:
        risk_premium_7d_avg = 0
        risk_premium_30d_avg = 0
        capital_at_risk_7d_avg = 0
        capital_at_risk_30d_avg = 0
    else:
        dt_7 = datetime.now() - timedelta(days=7)
        dt_30 = datetime.now() - timedelta(days=30)
        rp = RiskPremium.objects.filter(ilk=ilk).aggregate(
            risk_premium_7d_avg=Avg("risk_premium", filter=Q(datetime__gte=dt_7)),
            risk_premium_30d_avg=Avg("risk_premium", filter=Q(datetime__gte=dt_30)),
            capital_at_risk_7d_avg=Avg("capital_at_risk", filter=Q(datetime__gte=dt_7)),
            capital_at_risk_30d_avg=Avg(
                "capital_at_risk", filter=Q(datetime__gte=dt_30)
            ),
        )

        risk_premium_7d_avg = rp["risk_premium_7d_avg"] or 0
        risk_premium_30d_avg = rp["risk_premium_30d_avg"] or 0
        capital_at_risk_7d_avg = rp["capital_at_risk_7d_avg"] or 0
        capital_at_risk_30d_avg = rp["capital_at_risk_30d_avg"] or 0

    dt = datetime.now()

    IlkHistoricStats.objects.create(
        ilk=ilk,
        datetime=dt,
        timestamp=dt.timestamp(),
        total_debt=stats["total_debt"],
        vaults_count=stats["vaults_count"],
        weighted_collateralization_ratio=stats["weighted_collateralization_ratio"],
        total_locked=stats["total_locked"],
        protected_count=protected_count,
        protected_debt=protected_debt,
        capital_at_risk=stats["capital_at_risk"],
        risk_premium=stats["risk_premium"],
        risk_premium_7d_avg=risk_premium_7d_avg,
        risk_premium_30d_avg=risk_premium_30d_avg,
        capital_at_risk_7d_avg=capital_at_risk_7d_avg,
        capital_at_risk_30d_avg=capital_at_risk_30d_avg,
    )


def get_liquidation_curve(ilk, type="total"):
    liquidations = (
        VaultsLiquidation.objects.filter(ilk=ilk)
        .exclude(type="all")
        .order_by("drop", "total_debt")
        .values("drop", "total_debt", "type", "debt", "expected_price")
    )
    result = []

    for liquidation in liquidations:
        if type == "total":
            result.append(
                {
                    "protection_score": liquidation["type"],
                    "total_debt": liquidation["total_debt"],
                    "drop": liquidation["drop"],
                    "expected_price": liquidation["expected_price"],
                }
            )
        elif type == "bucket":
            result.append(
                {
                    "protection_score": liquidation["type"],
                    "total_debt": liquidation["debt"],
                    "drop": liquidation["drop"],
                    "expected_price": liquidation["expected_price"],
                }
            )
    return result


def get_debt_ceiling_historic_stats_for_ilk(ilk, days_ago):
    start_timestamp = get_date_timestamp_days_ago(days_ago)
    data = (
        RiskPremium.objects.filter(ilk=ilk, timestamp__gte=start_timestamp)
        .order_by("datetime")
        .annotate(
            dc=F("debt_ceiling"),
            dc_7d=F("debt_ceiling_7d_avg"),
            dc_30d=F("debt_ceiling_30d_avg"),
        )
        .values("datetime", "dc", "dc_7d", "dc_30d")
    )

    return data
