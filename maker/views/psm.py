# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from datetime import datetime, timedelta
from decimal import Decimal

import serpy
from django.db import connection
from django.db.models import Case, F, FloatField, Sum, Value, When
from django.db.models.functions import TruncHour
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Asset, Ilk, IlkHistoricStats, PSMDAISupply, UrnEventState
from maker.utils.views import PaginatedApiView, fetch_all, fetch_one

log = logging.getLogger(__name__)


class PSMEventsSerializer(serpy.DictSerializer):
    block_number = serpy.Field()
    datetime = serpy.Field()
    tx_hash = serpy.Field()
    principal = serpy.Field()

    symbol = serpy.MethodField()

    def get_symbol(self, obj):
        return obj["ilk"].split("-")[1]


class PSMEventsView(PaginatedApiView):
    """
    Get all events for psm
    """

    default_order = "-block_number"
    ordering_fields = ["block_number", "principal", "datetime"]
    serializer_class = PSMEventsSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return (
            UrnEventState.objects.filter(ilk=kwargs["ilk"])
            .annotate(principal=F("dart") / Decimal("1e18"))
            .values(
                "block_number",
                "datetime",
                "tx_hash",
                "principal",
                "ilk",
            )
        )


class PSMEventStatsView(APIView):
    def get(self, request, ilk):
        ilk_obj = get_object_or_404(Ilk, ilk=ilk, is_active=True, type="psm")

        days_ago = self.request.GET.get("days_ago")
        try:
            days_ago = int(days_ago)
        except (TypeError, ValueError):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        if days_ago not in [1, 7, 30]:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        sql = """
            SELECT
                DATE_TRUNC('day', datetime) as dt
                , CASE
                    WHEN dart > 0 THEN 'GENERATE'
                    ELSE 'PAYBACK'
                END AS operation
                , SUM(dart/1e18) as amount
            FROM maker_urneventstate
            WHERE datetime::date >= %s
                AND ilk = %s
            GROUP BY 1, 2
            ORDER BY 2
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


class PSMDAISupplyHistoryView(APIView):
    def get(self, request, ilk):
        ilk_obj = get_object_or_404(Ilk, ilk=ilk, is_active=True, type="psm")

        days_ago = self.request.GET.get("days_ago")
        try:
            days_ago = int(days_ago)
        except (TypeError, ValueError):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        if days_ago not in [7, 30, 90]:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        debts = (
            PSMDAISupply.objects.filter(
                ilk=ilk_obj.ilk, datetime__gte=datetime.now() - timedelta(days=days_ago)
            )
            .values("datetime", "total_supply")
            .order_by("-datetime")
        )

        return Response(debts, status.HTTP_200_OK)


class PSMsView(APIView):
    def get(self, request):
        days_ago = self.request.GET.get("days_ago")
        try:
            days_ago = int(days_ago)
        except (TypeError, ValueError):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        max_days_ago = 30
        if days_ago not in [1, 7, max_days_ago]:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        dt_hour_ago = (datetime.now() - timedelta(days=days_ago)).replace(
            second=0, microsecond=0, minute=0
        )

        ilks = Ilk.objects.filter(is_active=True).values_list("ilk", flat=True)

        sql = """
        SELECT SUM(a.total_debt) as debt
        FROM maker_ilkhistoricstats a
        JOIN (
            SELECT ilk, MAX(datetime) as datetime
            FROM maker_ilkhistoricstats
            WHERE ilk IN %s
            AND datetime > %s
            GROUP BY ilk
        ) b
        ON a.ilk = b.ilk AND a.datetime = b.datetime
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql, [tuple(ilks), datetime.now() - timedelta(days=max_days_ago + 1)]
            )
            total_debt = fetch_one(cursor)["debt"]

        total_debt_old = (
            IlkHistoricStats.objects.annotate(hour=TruncHour("datetime"))
            .filter(hour=dt_hour_ago)
            .aggregate(debt=Sum("total_debt"))["debt"]
        )

        data = (
            Ilk.objects.filter(type="psm")
            .annotate(
                share=F("dai_debt") / Value(total_debt),
                utilization=Case(
                    When(dc_iam_line=0, then=Value(0)),
                    default=F("dai_debt") / F("dc_iam_line"),
                    output_field=FloatField(),
                ),
            )
            .values(
                "ilk",
                "dai_debt",
                "collateral",
                "name",
                "share",
                "dc_iam_line",
                "utilization",
                "fee_in",
                "fee_out",
            )
            .order_by("-dai_debt")
        )

        stats = {
            "debt": Decimal("0"),
            "dc": Decimal("0"),
            "share": Decimal("0"),
        }
        stats_change = {
            "debt": Decimal("0"),
            "share": Decimal("0"),
            "dc": Decimal("0"),
        }

        for entry in data:
            ilk_stats = None
            try:
                ilk_stats = IlkHistoricStats.objects.annotate(
                    hour=TruncHour("datetime")
                ).get(hour=dt_hour_ago, ilk=entry["ilk"])
            except IlkHistoricStats.DoesNotExist:
                log.exception(
                    "Couldn't fetch IlkHistoricStats for %s at hour %s",
                    entry["ilk"],
                    dt_hour_ago,
                )

            symbol = entry["collateral"]
            if symbol == "PAX":
                symbol = "USDP"
            market_cap = Asset.objects.get(symbol=symbol).market_cap
            share_captured = entry["dai_debt"] / market_cap
            entry["share_captured"] = share_captured

            stats["debt"] += entry["dai_debt"]
            stats["dc"] += entry.get("dc_iam_line", 0) or 0
            stats["share"] += entry["share"]

            if ilk_stats:
                debt_diff = entry["dai_debt"] - ilk_stats.total_debt
                entry["debt_diff"] = debt_diff
                stats_change["debt"] += debt_diff
                if ilk_stats.dc_iam_line is not None:
                    dc_iam_line = entry.get("dc_iam_line", 0) or 0
                    dc_diff = dc_iam_line - ilk_stats.dc_iam_line
                    entry["dc_diff"] = dc_diff
                    stats_change["dc"] += dc_diff

                if total_debt_old:
                    stats_change["share"] += entry["share"] - (
                        ilk_stats.total_debt / total_debt_old
                    )

        stats["change"] = stats_change
        response = {
            "results": data,
            "stats": stats,
        }
        return Response(response, status.HTTP_200_OK)


class PSMsDAISupplyHistoryView(APIView):
    def get(self, request):
        days_ago = self.request.GET.get("days_ago")
        try:
            days_ago = int(days_ago)
        except (TypeError, ValueError):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        if days_ago not in [7, 30, 90]:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        ilks = list(
            Ilk.objects.filter(type="psm", is_active=True).values_list("ilk", flat=True)
        )

        sql = """
            SELECT
                  x.datetime
                , x.ilk
                , y.total_supply
            FROM (
                SELECT
                      a.datetime
                    , ilk
                FROM (
                    SELECT
                        DISTINCT(datetime)
                    FROM maker_psmdaisupply
                    WHERE ilk IN %s
                    AND datetime >= %s
                ) a
                CROSS JOIN UNNEST(%s) ilk
            ) x
            LEFT JOIN LATERAL (
                SELECT total_supply
                FROM maker_psmdaisupply b
                WHERE b.datetime <= x.datetime
                AND b.ilk = x.ilk
                ORDER BY b.datetime DESC
                LIMIT 1
            ) y
            ON 1=1
            ORDER BY x.datetime, x.ilk
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql, [tuple(ilks), datetime.now() - timedelta(days=days_ago), ilks]
            )
            supplies = fetch_all(cursor)

        return Response(supplies, status.HTTP_200_OK)


class PSMsEventStatsView(APIView):
    def get(self, request):
        days_ago = self.request.GET.get("days_ago")
        try:
            days_ago = int(days_ago)
        except (TypeError, ValueError):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        if days_ago not in [7, 30, 90]:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        ilks = Ilk.objects.filter(type="psm", is_active=True).values_list(
            "ilk", flat=True
        )

        sql = """
            SELECT
                ilk
                , DATE_TRUNC('day', datetime) as dt
                , CASE
                    WHEN dart > 0 THEN 'GENERATE'
                    ELSE 'PAYBACK'
                END AS operation
                , SUM(dart/1e18) as amount
            FROM maker_urneventstate
            WHERE datetime::date >= %s
                AND ilk IN %s
            GROUP BY 1, 2, 3
            ORDER BY 2, 1 DESC
        """
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                [
                    (datetime.now() - timedelta(days=days_ago)).date(),
                    tuple(ilks),
                ],
            )
            events = fetch_all(cursor)
        return Response(events, status.HTTP_200_OK)
