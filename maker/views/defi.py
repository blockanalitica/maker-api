# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import DEFILocked

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
