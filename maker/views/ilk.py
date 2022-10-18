# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from django.db import connection
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.utils.views import fetch_all

from ..models import Ilk, IlkHistoricStats, RiskPremium
from ..modules.ilk import (
    get_capital_at_risk_historic_stats_for_ilk,
    get_debt_ceiling_historic_stats_for_ilk,
    get_historic_stats_for_ilk,
    get_liquidation_curve,
    get_risk_premium_historic_stats_for_ilk,
    get_stats_for_ilk,
)
from ..modules.osm import get_osm_and_medianizer
from ..modules.risk_premium import (
    get_capital_at_risk_for_ilk,
    get_capital_at_risk_history_for_ilk,
    get_capital_at_risk_history_for_ilk_score,
)


class IlksView(APIView):
    """
    Get all tokens info
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 0))
        type = request.GET.get("type")
        dt = datetime.now() - timedelta(days=days_ago)
        filters = {}
        if type == "risky":
            filters = {"type": "asset"}
        ilks = (
            Ilk.objects.filter(is_active=True, **filters)
            .exclude(type="rwa")
            .values(
                "ilk",
                "name",
                "collateral",
                "lr",
                "locked",
                "dust",
                "stability_fee",
                "type",
                "dai_debt",
                "is_stable",
                "total_debt",
                "vaults_count",
                "capital_at_risk",
                "risk_premium",
            )
            .order_by("-dai_debt")
        )

        for ilk in ilks:
            try:
                stats = IlkHistoricStats.objects.filter(
                    ilk=ilk["ilk"], datetime__lte=dt
                ).latest()
            except IlkHistoricStats.DoesNotExist:
                stats = None

            if ilk["type"] in ["psm", "d3m"]:
                ilk["dai_debt"] = ilk["dai_debt"]
                if stats:
                    change = {
                        "total_debt_change": stats.total_debt,
                        "total_debt_diff": round(ilk["dai_debt"] - stats.total_debt),
                    }
                    ilk.update(change)

            else:
                ilk["dai_debt"] = ilk["total_debt"]
                if ilk["capital_at_risk"]:
                    ilk["capital_at_risk_change"] = stats.capital_at_risk
                    ilk["capital_at_risk_diff"] = round(
                        ilk["capital_at_risk"] - stats.capital_at_risk
                    )
                if ilk["risk_premium"]:
                    ilk["risk_premium_change"] = stats.risk_premium
                    ilk["risk_premium_diff"] = round(
                        ilk["risk_premium"] - stats.risk_premium, 2
                    )

                if stats:
                    change = {
                        "total_debt_change": stats.total_debt,
                        "total_locked_change": stats.total_locked,
                        "vaults_count_change": stats.vaults_count,
                        "total_debt_diff": round(ilk["total_debt"] - stats.total_debt),
                        "total_locked_diff": round(
                            ilk["locked"] - (stats.total_locked or 0)
                        ),
                        "vaults_count_diff": ilk["vaults_count"]
                        - (stats.vaults_count or 0),
                    }
                    ilk.update(change)

        return Response(ilks, status.HTTP_200_OK)


class IlkView(APIView):
    """
    Get ilk
    """

    def get(self, request, ilk):
        ilk = get_object_or_404(Ilk, ilk=ilk, is_active=True)
        data = {
            "ilk": ilk.ilk,
            "name": ilk.name,
            "collateral": ilk.collateral,
            "lr": ilk.lr,
            "type": ilk.type,
            "locked": ilk.locked,
            "dust": ilk.dust,
            "stability_fee": ilk.stability_fee,
            "debt_ceiling": ilk.debt_ceiling,
            "dc_iam_line": ilk.dc_iam_line,
            "utilization": ilk.dai_debt / ilk.dc_iam_line,
            "hole": ilk.hole,
        }

        return Response(data, status.HTTP_200_OK)


class IlkStatsView(APIView):
    """
    Get ilk stats
    """

    def get(self, request, ilk):
        days_ago = int(request.GET.get("days_ago", 0))
        data = get_stats_for_ilk(ilk, days_ago)
        return Response(data, status.HTTP_200_OK)


class IlkHistoricStatsView(APIView):
    """
    Get ilk stats
    """

    def get(self, request, ilk):
        days_ago = int(request.GET.get("days_ago", 30))
        stat_type = request.GET.get("type", "total_debt")
        if stat_type == "capital_at_risk":
            data = get_capital_at_risk_historic_stats_for_ilk(ilk, days_ago)
        elif stat_type == "risk_premium":
            data = get_risk_premium_historic_stats_for_ilk(ilk, days_ago)
        elif stat_type == "debt_ceiling":
            data = get_debt_ceiling_historic_stats_for_ilk(ilk, days_ago)
        else:
            data = get_historic_stats_for_ilk(ilk, stat_type, days_ago)
        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class IlkOSMView(APIView):
    """
    Get OSM and medianizer for ilk
    """

    def get(self, request, ilk):
        ilk = get_object_or_404(Ilk, ilk=ilk)
        data = get_osm_and_medianizer(ilk.collateral)
        return Response(data, status.HTTP_200_OK)


class IlkLiquidationCurveView(APIView):
    """
    Get liquidatin curve
    """

    def get(self, request, ilk):
        type = request.GET.get("type", "total")
        data = get_liquidation_curve(ilk, type=type)

        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class IlkCapitalAtRiskView(APIView):
    """
    Get capital at risk
    """

    def get(self, request, ilk):
        days_ago = int(request.GET.get("days_ago", 1))
        data = get_capital_at_risk_for_ilk(ilk, days_ago=days_ago)

        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class IlkCapitalAtRiskChartView(APIView):
    """
    Get capital at risk
    """

    def get(self, request, ilk):
        days_ago = int(request.GET.get("days_ago", 30))
        type = request.GET.get("type", "total")

        if type == "protection_score":
            data = get_capital_at_risk_history_for_ilk_score(ilk, days_ago)
        else:
            data = get_capital_at_risk_history_for_ilk(ilk, days_ago)
        response = {
            "results": data,
            "stats": get_capital_at_risk_for_ilk(ilk, days_ago=days_ago),
        }
        return Response(response, status.HTTP_200_OK)


class IlkRiskPremiumModelChartView(APIView):
    """
    Get risk premium
    """

    def get(self, request, ilk):
        rp = RiskPremium.objects.filter(ilk=ilk).latest()
        response = {
            "results": rp.data,
            "debt_ceiling": rp.debt_ceiling,
            "risk_premium": rp.risk_premium,
            "total_debt_dai": rp.total_debt_dai,
        }
        return Response(response, status.HTTP_200_OK)


class IlkEventStatsView(APIView):
    def get(self, request, ilk):
        ilk_obj = get_object_or_404(Ilk, ilk=ilk, is_active=True)

        days_ago = int(request.GET.get("days_ago", 7))
        if days_ago not in [1, 7, 30]:
            raise Http404()

        sql = """
            SELECT
                  operation
                , DATE_TRUNC('day', datetime) as dt
                , CASE
                    WHEN operation IN ('DEPOSIT', 'WITHDRAW')
                    THEN SUM(collateral)
                    ELSE SUM(principal)
                  END as amount
                , CASE
                    WHEN operation IN ('DEPOSIT', 'WITHDRAW')
                    THEN SUM(collateral * osm_price)
                    ELSE SUM(principal)
                  END as amount_usd
            FROM maker_rawevent
            WHERE datetime::date >= %s
              AND ilk = %s
              AND operation IN ('DEPOSIT', 'WITHDRAW', 'GENERATE', 'PAYBACK')
            GROUP BY 1, 2
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    (datetime.now() - timedelta(days=days_ago)).date(),
                    ilk_obj.ilk,
                ],
            )
            events = fetch_all(cursor)

        return Response(events, status.HTTP_200_OK)