# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

import serpy
from django.core.cache import cache
from django.db.models import F, Q
from django.db.models.aggregates import Avg, Count, Func, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncQuarter, TruncWeek
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Liquidation, VaultsLiquidation, VaultsLiquidationHistory
from maker.modules.liquidations import get_liquidations_per_drop_data
from maker.modules.slippage import get_slippage_for_lp, get_slippage_to_dai
from maker.utils.views import PaginatedApiView

from ..models import Auction, AuctionAction, Ilk
from ..modules.auctions import (
    get_auction,
    get_auction_dur_stats,
    get_auction_throughput_data_for_ilk,
    get_ilk_auctions_per_date,
    get_stair_step_exponential,
)


class SimulatedLiquidationsPerDropViewSerializer(serpy.DictSerializer):
    drop = serpy.Field()
    high = serpy.Field()
    high_diff = serpy.Field()
    previous_high = serpy.Field()
    low = serpy.Field()
    low_diff = serpy.Field()
    previous_low = serpy.Field()
    medium = serpy.Field()
    medium_diff = serpy.Field()
    previous_medium = serpy.Field()
    total = serpy.Field()
    total_diff = serpy.Field()
    previous_total = serpy.Field()


class AuctionThroughputSerializer(serpy.DictSerializer):
    stats = serpy.Field()
    simulations = serpy.Field()
    stairstep_exponential = serpy.Field()


class LiquidationsSerializer(serpy.DictSerializer):
    id = serpy.Field()
    timestamp = serpy.Field()
    datetime = serpy.Field()
    block_number = serpy.Field()
    tx_hash = serpy.StrField()
    debt_symbol = serpy.StrField()
    debt_token_price = serpy.Field()
    debt_repaid = serpy.Field()
    debt_repaid_usd = serpy.Field()

    collateral_symbol = serpy.StrField()
    ilk = serpy.StrField()
    collateral_token_price = serpy.Field()
    collateral_seized = serpy.Field()
    collateral_seized_usd = serpy.Field()

    protocol = serpy.Field()
    finished = serpy.Field()
    uid = serpy.Field()


class AuctionSerializer(serpy.DictSerializer):
    ilk = serpy.Field()
    uid = serpy.Field()
    auction_start = serpy.Field()
    vault = serpy.Field()
    available_collateral = serpy.Field()
    penalty = serpy.Field()
    sold_collateral = serpy.Field()
    recovered_debt = serpy.Field()
    auction_end = serpy.Field()
    duration = serpy.Field()
    penalty_fee = serpy.Field()
    debt_liquidated = serpy.Field()
    penalty_fee_per = serpy.Field()
    coll_returned = serpy.Field()
    symbol = serpy.Field()
    osm_settled_avg = serpy.Field()
    mkt_settled_avg = serpy.Field()


class LiquidationsPerDaySerializer(serpy.DictSerializer):
    auction_date = serpy.Field()
    total_auctions = serpy.Field()
    total_debt = serpy.Field()
    total_penalty_fee = serpy.Field()
    recovered_debt = serpy.StrField()
    penalty_fee_per = serpy.StrField()


class KeepersField(serpy.Field):
    def to_value(self, value):
        return AuctionAction.objects.filter(ilk=value).aggregate(
            count=Count("keeper", distinct=True, filter=Q(type="kick", status=1))
        )["count"]


class TakersField(serpy.Field):
    def to_value(self, value):
        return AuctionAction.objects.filter(ilk=value).aggregate(
            count=Count("caller", distinct=True, filter=Q(type="take", status=1))
        )["count"]


class LiquidationsPerIlksSerializer(serpy.DictSerializer):
    ilk = serpy.Field()
    total_auctions = serpy.Field()
    total_debt = serpy.Field()
    total_penalty_fee = serpy.Field()
    recovered_debt = serpy.StrField()
    penalty_fee_per = serpy.StrField()
    keepers = KeepersField()
    takers = TakersField()
    symbol = serpy.MethodField()

    def get_symbol(self, obj):
        return obj["ilk"].split("-")[0]


class LiquidationsView(PaginatedApiView):
    """
    Get all liquidations
    """

    default_order = "-block_number"
    ordering_fields = ["collateral_seized_usd", "debt_repaid_usd"]
    serializer_class = LiquidationsSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        days_ago = query_params.get("days_ago")
        timestamp = 0
        if days_ago:
            try:
                days_ago = int(days_ago)
            except (TypeError, ValueError):
                return Response(None, status.HTTP_400_BAD_REQUEST)
            if days_ago == 0:
                timestamp = 0
            else:
                timestamp = (datetime.now() - timedelta(days=int(days_ago))).timestamp()
        return (
            Liquidation.objects.filter(timestamp__gte=timestamp, protocol="maker")
            .annotate(
                collateral_seized_usd=Sum(
                    F("collateral_seized") * F("collateral_token_price")
                ),
                debt_repaid_usd=Sum(F("debt_repaid") * F("debt_token_price")),
            )
            .values(
                "id",
                "timestamp",
                "datetime",
                "block_number",
                "tx_hash",
                "debt_symbol",
                "debt_token_price",
                "debt_repaid",
                "debt_repaid_usd",
                "collateral_symbol",
                "collateral_token_price",
                "collateral_seized",
                "collateral_seized_usd",
                "protocol",
                "ilk",
                "finished",
                "uid",
            )
        )


class LiquidationsPeriodView(APIView):
    def get(self, request):
        try:
            days_ago = int(request.GET.get("days_ago", 30))
        except (TypeError, ValueError):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        if days_ago == 0:
            timestamp = 0
        else:
            timestamp = (datetime.now() - timedelta(days=days_ago)).timestamp()

        if days_ago == 0:
            trunc = TruncQuarter
        elif days_ago > 180:
            trunc = TruncMonth
        elif days_ago > 30:
            trunc = TruncWeek
        else:
            trunc = TruncDay

        base_queryset = Liquidation.objects.filter(
            finished=True, timestamp__gte=timestamp, protocol="maker"
        )
        queryset = (
            base_queryset.annotate(date=trunc("datetime"))
            .values("ilk", "date")
            .annotate(
                total_collateral_seized_usd=Sum(
                    F("collateral_seized") * F("collateral_token_price")
                ),
            )
            .order_by("ilk", "date")
        )

        aggregates = base_queryset.aggregate(
            count=Count("id"),
            total_collateral_seized_usd=Sum(
                F("collateral_seized") * F("collateral_token_price")
            ),
            total_debt_repaid_usd=Sum(F("debt_repaid") * F("debt_token_price")),
            penalty_fee=Sum("penalty"),
            penalized_collateral=Sum(
                F("collateral_seized") * F("collateral_token_price"),
                filter=Q(penalty__gt=0),
            ),
            penalized_debt=Sum(
                F("debt_repaid") * F("debt_token_price"), filter=Q(penalty__gt=0)
            ),
        )

        response = {
            "results": list(queryset),
            "totals": {
                "total_collateral_seized_usd": aggregates[
                    "total_collateral_seized_usd"
                ],
                "total_debt_repaid_usd": aggregates["total_debt_repaid_usd"],
                "count": aggregates["count"],
                "penalty_fee": aggregates["penalty_fee"],
                "penalized_collateral": aggregates["penalized_collateral"],
                "penalized_debt": aggregates["penalized_debt"],
            },
        }
        return Response(response, status.HTTP_200_OK)


class LiquidationsAssetView(APIView):
    def get(self, request):
        days_ago = request.GET.get("days_ago")
        timestamp = 0
        if days_ago:
            try:
                days_ago = int(days_ago)
            except (TypeError, ValueError):
                return Response(None, status.HTTP_400_BAD_REQUEST)
            if days_ago == 0:
                timestamp = 0
            else:
                timestamp = (datetime.now() - timedelta(days=int(days_ago))).timestamp()

        data = (
            Liquidation.objects.filter(
                finished=True, timestamp__gte=timestamp, protocol="maker"
            )
            .values("collateral_symbol")
            .annotate(
                collateral_seized_total=Sum("collateral_seized"),
                collateral_seized_usd=Sum(
                    F("collateral_seized") * F("collateral_token_price")
                ),
            )
            .order_by("collateral_symbol")
        )
        return Response(data, status.HTTP_200_OK)


class AuctionsThroughputView(APIView):
    def get(self, request):
        data = []
        percent_liquidated = float(request.GET.get("percent_liquidated", 20)) / 100
        ilks = Ilk.objects.active().exclude(collateral__in=["PSM", "DIRECT"])
        for ilk in ilks.exclude(collateral__contains="RWA"):
            auction_data = get_auction_throughput_data_for_ilk(ilk)
            if not auction_data["current_hole"]:
                continue
            dur_stats = get_auction_dur_stats(
                auction_data["cut"],
                auction_data["buf"],
                percent_liquidated,
                auction_data["step"],
                auction_data["current_hole"],
                auction_data["dai"],
            )
            auction_data["debt_exposure_share"] = dur_stats["debt_exposure_share"]
            auction_data["auction_cycle"] = dur_stats["auction_cycle"]
            auction_data["auction_dur"] = dur_stats["auction_dur"]
            auction_data["auction_dur_m"] = dur_stats["auction_dur_m"]
            auction_data["dai"] = round(auction_data["dai"])
            data.append(auction_data)
        return Response(data, status.HTTP_200_OK)


class AuctionThroughputView(APIView):
    def get(self, request, ilk):
        ilk = Ilk.objects.get(ilk=ilk)
        debt = float(request.GET.get("debt", ilk.dai_debt))
        sim_hole = float(request.GET.get("sim_hole", ilk.hole))
        percent_liquidated = float(request.GET.get("percent_liquidated", 20)) / 100
        buf = float(request.GET.get("buf", ilk.buf)) / 100
        cut = float(request.GET.get("cut", ilk.cut)) / 100
        step = float(request.GET.get("step", ilk.step))
        tail = float(request.GET.get("tail", ilk.tail))
        cusp = float(request.GET.get("cusp", ilk.cusp))
        previous_duration = request.GET.get("previous_duration")
        previous_cycle = request.GET.get("previous_cycle")
        previous_exposure = request.GET.get("previous_exposure")
        previous_slippage = request.GET.get("previous_slippage")
        sim_dur_stats = get_auction_dur_stats(
            cut, buf, percent_liquidated, step, sim_hole, debt
        )

        stairstep_exponential = get_stair_step_exponential(buf, cut, step, tail, cusp)
        if ilk.type == "lp" or "GUNIV3DAIUSDC" in ilk.collateral:
            sim_slippage = get_slippage_for_lp(ilk.collateral, sim_hole)
        else:
            sim_slippage = get_slippage_to_dai(ilk.collateral, sim_hole)

        stats = get_auction_throughput_data_for_ilk(ilk)
        stats["tail"] = tail
        stats["buf"] = buf
        stats["cusp"] = cusp
        simulations = {}
        simulations["auction_dur"] = sim_dur_stats["auction_dur"]
        simulations["auction_dur_m"] = sim_dur_stats["auction_dur_m"]
        simulations["auction_cycle"] = sim_dur_stats["auction_cycle"]
        simulations["debt_exposure_share"] = sim_dur_stats["debt_exposure_share"]
        simulations["sim_slippage"] = sim_slippage
        if previous_cycle:
            simulations["dur_diff"] = sim_dur_stats["auction_dur_m"] - Decimal(
                previous_duration
            )
            simulations["cycle_diff"] = Decimal(
                sim_dur_stats["auction_cycle"]
            ) - Decimal(previous_cycle)

            simulations["exposure_diff"] = round(
                (
                    Decimal(sim_dur_stats["debt_exposure_share"])
                    - Decimal(previous_exposure)
                ),
                3,
            )
            simulations["slippage_diff"] = round(
                (sim_slippage - Decimal(previous_slippage)), 3
            )
        data = {
            "stats": stats,
            "simulations": simulations,
            "stairstep_exponential": stairstep_exponential,
        }

        serializer = AuctionThroughputSerializer(data)
        return Response(serializer.data, status.HTTP_200_OK)


class SimulatedLiquidationsPerDropTableView(APIView):
    def get(self, request):
        try:
            days_ago = int(request.GET.get("days_ago"))
        except (ValueError, TypeError):
            days_ago = 1
        ilk = request.GET.get("ilk")
        data = get_liquidations_per_drop_data(days_ago, ilk)
        serializer = SimulatedLiquidationsPerDropViewSerializer(data, many=True)
        return Response(serializer.data, status.HTTP_200_OK)


class SimulatedLiquidationsPerDropView(APIView):
    def get(self, request):
        try:
            days_ago = int(request.GET.get("days_ago"))
        except (ValueError, TypeError):
            days_ago = 90
        if days_ago > 365:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        drops = [20, 30, 40]
        per_drop_data = (
            VaultsLiquidationHistory.objects.filter(
                datetime__gte=datetime.now() - timedelta(days=days_ago),
                drop__in=drops,
            )
            .values("drop", "datetime")
            .order_by("drop", "datetime")
            .annotate(amount=Sum("total_debt"))
        )
        return Response(per_drop_data, status.HTTP_200_OK)


class LiquidationView(APIView):
    def get(self, request, ilk, uid):
        kicks, takes, auction = get_auction(ilk, uid)
        response = {"kicks": kicks, "takes": takes, "auction": auction}
        return Response(response, status.HTTP_200_OK)


class LiquidationsPerDateView(PaginatedApiView):
    """
    Get all aggregate liquidations per date
    """

    default_order = "-auction_date"
    ordering_fields = [
        "total_auctions",
        "total_debt",
        "total_penalty_fee",
        "recovered_debt",
        "auction_date",
        "penalty_fee_per",
    ]
    serializer_class = LiquidationsPerDaySerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return (
            Auction.objects.annotate(
                auction_date=Func(F("auction_start"), function="DATE")
            )
            .values("auction_date")
            .annotate(
                total_auctions=Count("id"),
                total_debt=Sum("debt_liquidated"),
                duration_avg=Avg("duration"),
                total_penalty_fee=Sum("penalty_fee"),
                recovered_debt=Sum("recovered_debt"),
            )
            .annotate(
                penalty_fee_per=F("total_penalty_fee") / F("total_debt"),
            )
        )


class LiquidationsPerDateIlksView(PaginatedApiView):
    """
    Get all aggregate ilk liquidations per date
    """

    default_order = "-total_auctions"
    ordering_fields = [
        "total_auctions",
        "total_debt",
        "total_penalty_fee",
        "recovered_debt",
        "auction_start",
        "penalty_fee_per",
    ]
    serializer_class = LiquidationsPerIlksSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return (
            Auction.objects.filter(auction_start__date=kwargs["date"])
            .values("ilk")
            .annotate(
                total_auctions=Count("id"),
                total_debt=Sum("debt_liquidated"),
                duration_avg=Avg("duration"),
                total_penalty_fee=Sum("penalty_fee"),
                recovered_debt=Sum("recovered_debt"),
                keepers=F("ilk"),
                takers=F("ilk"),
            )
            .annotate(
                penalty_fee_per=F("total_penalty_fee") / F("total_debt"),
            )
        )


class LiquidationsPerDateIlkView(PaginatedApiView):
    """
    Get all liquidations per ilk
    """

    default_order = "-debt_liquidated"
    ordering_fields = [
        "debt",
        "penalty_fee",
        "debt_liquidated",
        "recovered_debt",
        "penalty_fee_per",
        "coll_returned",
        "duration",
    ]
    serializer_class = AuctionSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return (
            Auction.objects.filter(
                ilk=kwargs["ilk"], auction_start__date=kwargs["date"]
            )
            .annotate(
                penalty_fee_per=F("penalty_fee") / F("debt_liquidated"),
                coll_returned=(F("available_collateral") / F("kicked_collateral")),
            )
            .values(
                "ilk",
                "uid",
                "auction_start",
                "vault",
                "debt",
                "available_collateral",
                "penalty",
                "sold_collateral",
                "recovered_debt",
                "auction_end",
                "duration",
                "penalty_fee",
                "debt_liquidated",
                "penalty_fee_per",
                "coll_returned",
                "symbol",
                "osm_settled_avg",
                "mkt_settled_avg",
            )
        )


class LiquidationsPerIlksView(PaginatedApiView):
    """
    Get all liquidations per ilks
    """

    default_order = "-total_debt"
    ordering_fields = [
        "total_auctions",
        "total_debt",
        "total_penalty_fee",
        "recovered_debt",
        "auction_date",
        "penalty_fee_per",
        "ilk",
    ]
    serializer_class = LiquidationsPerIlksSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return (
            Auction.objects.values("ilk")
            .annotate(
                total_auctions=Count("id"),
                total_debt=Sum("debt_liquidated"),
                duration_avg=Avg("duration"),
                total_penalty_fee=Sum("penalty_fee"),
                recovered_debt=Sum("recovered_debt"),
                keepers=F("ilk"),
                takers=F("ilk"),
            )
            .annotate(
                penalty_fee_per=F("total_penalty_fee") / F("total_debt"),
            )
        )


class LiquidationsPerIlkView(PaginatedApiView):
    """
    Get all liquidations per ilk
    """

    default_order = "uid"
    ordering_fields = [
        "debt",
        "penalty_fee",
        "debt_liquidated",
        "recovered_debt",
        "penalty_fee_per",
        "coll_returned",
        "duration",
    ]
    serializer_class = AuctionSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return (
            Auction.objects.filter(ilk=kwargs["ilk"])
            .annotate(
                penalty_fee_per=F("penalty_fee") / F("debt_liquidated"),
                coll_returned=(F("available_collateral") / F("kicked_collateral")),
            )
            .values(
                "ilk",
                "uid",
                "auction_start",
                "vault",
                "debt",
                "available_collateral",
                "penalty",
                "sold_collateral",
                "recovered_debt",
                "auction_end",
                "duration",
                "penalty_fee",
                "debt_liquidated",
                "penalty_fee_per",
                "coll_returned",
                "symbol",
                "osm_settled_avg",
                "mkt_settled_avg",
            )
        )


class ActionsPerIlkPerDateView(APIView):
    """
    Get aggregated keepers data
    """

    def get(self, request):
        filter_date = request.GET.get("date")
        ilk = request.GET.get("ilk")
        data = get_ilk_auctions_per_date(ilk, filter_date)
        return Response(data, status.HTTP_200_OK)


class KeepersView(APIView):
    """
    Get aggregated keepers data
    """

    def get(self, request):
        filter_date = request.GET.get("date")
        vault_ilk = request.GET.get("ilk")
        results = []
        stats = defaultdict(Decimal)
        keepers = defaultdict(lambda: defaultdict(Decimal))

        query_filter = {
            "type": "kick",
        }
        if filter_date:
            query_filter["datetime__date"] = filter_date
        if vault_ilk:
            query_filter["ilk"] = vault_ilk
        total_debt = AuctionAction.objects.filter(**query_filter).aggregate(
            amount=Sum("debt")
        )
        keeper_data = (
            AuctionAction.objects.filter(status=1, **query_filter)
            .order_by("keeper")
            .values("keeper", "debt", "incentives", "datetime")
        )

        for action in keeper_data:
            keepers[action["keeper"]]["debt"] += action["debt"]
            keepers[action["keeper"]]["incentives"] += action["incentives"]
            keepers[action["keeper"]]["count"] += 1
            keepers[action["keeper"]]["last_active"] = action["datetime"]

        for keeper, values in keepers.items():
            stats["debt_repaid"] += values["debt"]
            stats["kick_count"] += values["count"]
            stats["incentives"] += values["incentives"]
            results.append(
                {
                    "wallet": keeper,
                    "debt_liquidated": values["debt"],
                    "incentives": values["incentives"],
                    "count": values["count"],
                    "share": values["debt"] / total_debt["amount"] * 100,
                    "last_active": values["last_active"],
                }
            )

        stats["unique_keepers"] = len(results)
        response = {
            "results": results,
            "stats": stats,
        }
        return Response(response, status.HTTP_200_OK)


class TakersView(APIView):
    def get(self, request):
        filter_date = request.GET.get("date")
        vault_ilk = request.GET.get("ilk")
        results = []
        stats = defaultdict(Decimal)
        takers = defaultdict(lambda: defaultdict(Decimal))
        query_filter = {
            "type": "take",
        }
        if filter_date:
            query_filter["datetime__date"] = filter_date
        if vault_ilk:
            query_filter["ilk"] = vault_ilk

        total_debt = AuctionAction.objects.filter(**query_filter).aggregate(
            amount=Sum("recovered_debt")
        )
        taker_data = (
            AuctionAction.objects.filter(status=1, recovered_debt__gt=0, **query_filter)
            .order_by("datetime")
            .values("caller", "recovered_debt", "datetime")
        )
        for action in taker_data:
            takers[action["caller"]]["debt"] += action["recovered_debt"]
            takers[action["caller"]]["count"] += 1
            takers[action["caller"]]["last_active"] = action["datetime"]

        for caller, values in takers.items():
            stats["debt_repaid"] += values["debt"]
            stats["kick_count"] += values["count"]
            results.append(
                {
                    "wallet": caller,
                    "debt_liquidated": values["debt"],
                    "count": values["count"],
                    "share": values["debt"] / total_debt["amount"] * 100,
                    "last_active": values["last_active"],
                }
            )

        stats["unique_takers"] = len(results)
        response = {
            "results": results,
            "stats": stats,
        }
        return Response(response, status.HTTP_200_OK)


class AuctionTakersKeepersView(APIView):
    def get(self, request):
        cache_key = "AuctionTakersKeepersView.keepers_takers_data"
        data = cache.get(cache_key, [])
        date_start = None
        if data:
            # We're up to date, just return response
            if data[-1]["date"] == date.today():
                return Response(data, status.HTTP_200_OK)

            date_start = data[-1]["date"] + timedelta(days=1)

        if not date_start:
            first_auction = Auction.objects.all().order_by("auction_start").first()
            date_start = first_auction.auction_start.date()

        dt = date_start

        while dt <= date.today():
            auctions = Auction.objects.filter(auction_start__date__lt=dt)[
                :100
            ].aggregate(
                unique_keepers=Count(
                    "actions__keeper", distinct=True, filter=Q(actions__type="kick")
                ),
                unique_takers=Count(
                    "actions__caller", distinct=True, filter=Q(actions__type="take")
                ),
            )
            auctions["date"] = dt
            data.append(auctions)
            dt += timedelta(days=1)

        cache.set(cache_key, data, None)
        return Response(data, status.HTTP_200_OK)


class LiquidationCurveView(APIView):
    def get(self, request):
        mapping = {
            "WETH": ["ETH-A", "ETH-B", "ETH-C"],
            "WBTC": ["WBTC-A", "WBTC-B", "WBTC-C"],
            "stETH": ["WSTETH-A", "WSTETH-B"],
        }
        data = {}
        for key, ilks in mapping.items():
            drops = (
                VaultsLiquidation.objects.filter(
                    ilk__in=ilks,
                    drop__lte=50,
                    type__in=[
                        "high",
                        "medium",
                        "low",
                    ],
                )
                .values("drop")
                .annotate(amount=Sum("total_debt"))
                .order_by("drop")
            )
            data[key] = list(drops)
        return Response(data, status.HTTP_200_OK)
