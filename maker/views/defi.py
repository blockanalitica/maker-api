# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models.functions import TruncDay
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import DEFILocked
from maker.utils.http import retry_get_json

from ..modules.defi import get_current_rates, get_rates


class RatesView(APIView):
    """
    Get all rates
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 7))
        symbol = request.GET.get("symbol", "DAI")
        data = get_rates(symbol, days_ago)
        return Response(
            {"results": data, "current": get_current_rates(symbol, days_ago=days_ago)},
            status.HTTP_200_OK,
        )


class DEFILockedView(APIView):
    """
    Get tvl
    """

    def get(self, request, symbol):
        days_ago = int(request.GET.get("days_ago", 7))
        d = (datetime.now() - timedelta(days=days_ago)).date()
        locked = (
            DEFILocked.objects.filter(
                underlying_symbol=symbol, date__gte=d, balance__gt=0
            )
            .values("protocol", "date", "balance")
            .order_by("datetime")
        )
        return Response(
            {"results": locked},
            status.HTTP_200_OK,
        )


class ETHMarketShareView(APIView):
    def get(self, request):
        eth_correlated = ["stETH", "wstETH", "WETH", "ETH", "rETH"]
        data = defaultdict(Decimal)
        for protocol in (
            DEFILocked.objects.filter(underlying_symbol__in=eth_correlated)
            .exclude(protocol="euler")
            .order_by("protocol")
            .distinct("protocol")
            .values_list("protocol", flat=True)
        ):
            for symbol in eth_correlated:
                try:
                    token_balance = (
                        DEFILocked.objects.filter(
                            protocol=protocol, underlying_symbol=symbol
                        )
                        .latest()
                        .balance
                    )
                except DEFILocked.DoesNotExist:
                    token_balance = 0
                protocol_key = protocol
                if "aave" in protocol:
                    protocol_key = "aave"
                if "compound" in protocol:
                    protocol_key = "compound"
                data[protocol_key] += token_balance
        results = [{"protocol": k, "balance": v} for k, v in data.items()]
        return Response(
            {"results": results},
            status.HTTP_200_OK,
        )


class ETHMarketShareHistoricView(APIView):
    def get(self, request):
        eth_correlated = ["stETH", "wstETH", "WETH", "ETH", "rETH"]
        days_ago = int(request.GET.get("days_ago", 7))
        data = defaultdict(lambda: defaultdict(Decimal))
        d = (datetime.now() - timedelta(days=days_ago)).date()
        entries = (
            DEFILocked.objects.annotate(dt=TruncDay("datetime"))
            .filter(underlying_symbol__in=eth_correlated, date__gte=d)
            .exclude(protocol="euler")
            .order_by("protocol", "date", "underlying_symbol")
            .distinct("protocol", "date", "underlying_symbol")
            .values("protocol", "date", "balance", "underlying_symbol")
        )
        for entry in entries:
            protocol_key = entry["protocol"]
            if "aave" in protocol_key:
                protocol_key = "aave"
            if "compound" in protocol_key:
                protocol_key = "compound"
            data[entry["date"]][protocol_key] += entry["balance"]

        results = []

        for date, values in data.items():
            for protocol, balance in values.items():
                results.append({"dt": date, "protocol": protocol, "balance": balance})
        return Response(
            {"results": results},
            status.HTTP_200_OK,
        )


class ETHMarketShareRouterView(APIView):
    def get(self, request):
        url = "https://makerdao-fyi-api.blockanalitica.com/v1/defi/eth-captured/"
        data = retry_get_json(url)
        return Response(
            {"results": data},
            status.HTTP_200_OK,
        )


class ETHMarketShareHistoricRouterView(APIView):
    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 7))
        url = (
            "https://makerdao-fyi-api.blockanalitica.com/v1/defi/eth-captured-historic/"
        )
        url += f"?days_ago={days_ago}"
        data = retry_get_json(url)
        return Response(
            {"results": data},
            status.HTTP_200_OK,
        )
