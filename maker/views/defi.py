# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import DEFILocked

from ..modules.defi import get_current_rates, get_rates
from collections import defaultdict
from decimal import Decimal


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
