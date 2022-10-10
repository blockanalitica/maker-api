# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import MakerAsset

from ..modules.osm import get_osm_and_medianizer, get_price_history


class OSMAsset(APIView):
    """
    Get OSM and medianizer for symbol
    """

    def get(self, request, symbol):
        data = get_osm_and_medianizer(symbol)
        return Response(data, status.HTTP_200_OK)


class OSMTableView(APIView):
    def get(self, request):

        assets = []
        symbols = (
            MakerAsset.objects.filter(
                is_active=True,
                is_stable=False,
                type="asset",
            )
            .values_list("symbol", flat=True)
            .order_by("symbol")
        )
        for symbol in symbols:
            assets.append(get_osm_and_medianizer(symbol))
        lps = []
        symbols = (
            MakerAsset.objects.filter(
                is_active=True,
                is_stable=False,
                type="lp",
            )
            .values_list("symbol", flat=True)
            .order_by("symbol")
        )
        for symbol in symbols:
            lps.append(get_osm_and_medianizer(symbol))
        data = {"assets": assets, "lps": lps}
        return Response(data, status.HTTP_200_OK)


class OracleHistoricStatsView(APIView):
    def get(self, request, symbol):
        days_ago = int(request.GET.get("days_ago"))
        data = get_price_history(symbol, days_ago)
        return Response(data, status.HTTP_200_OK)
