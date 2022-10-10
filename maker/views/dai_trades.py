# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import DAITrade
from maker.modules.dai_trades import (
    get_stats,
    trade_data_daily,
    trade_data_for_last_day,
    trade_volume_data,
    trade_volume_data_per_exchange,
)


class DAITradesLastDayView(APIView):
    def get(self, request):
        data = trade_data_for_last_day()
        return Response(data, status.HTTP_200_OK)


class DAITradesVolumeView(APIView):
    def get(self, request):
        data = trade_volume_data()
        return Response(data, status.HTTP_200_OK)


class DAITradesVolumePerExchangeView(APIView):
    def get(self, request):
        data = trade_volume_data_per_exchange()
        return Response(data, status.HTTP_200_OK)


class DAITradesDailyView(APIView):
    def get(self, request):
        data = trade_data_daily()
        return Response(data, status.HTTP_200_OK)


class DAITradesLastHoursView(APIView):
    def get(self, request):
        dt = datetime.now() - timedelta(hours=2)
        trades = (
            DAITrade.objects.filter(datetime__gte=dt)
            .values()
            .order_by("exchange", "datetime")
        )
        return Response(trades, status.HTTP_200_OK)


class DAITradesStatsView(APIView):
    def get(self, request):
        data = get_stats()
        return Response(data, status.HTTP_200_OK)
