# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..modules.d3m import aave, compound
from ..modules.d3m.d3m import get_d3m_stats, get_protocol_stats


class D3MsView(APIView):
    """
    Get D3Ms
    """

    def get(self, request):
        stats = get_d3m_stats()
        d3ms = [aave.get_d3m_short_info(), compound.get_d3m_short_info()]

        data = {"results": d3ms, "stats": stats}
        return Response(data, status.HTTP_200_OK)


class D3MView(APIView):
    """
    Get protocol D3M
    """

    def get(self, request, protocol):
        stats = get_protocol_stats(protocol)
        data = {"stats": stats}
        return Response(data, status.HTTP_200_OK)


class D3MHistoricRatesView(APIView):
    """
    Get protocol D3M
    """

    def get(self, request, protocol):
        days_ago = int(request.GET.get("days_ago", 30))
        if protocol == "aave":
            data = aave.get_historic_rates(days_ago)
        else:
            data = compound.get_historic_rates(days_ago)
        return Response(data, status.HTTP_200_OK)


class D3MComputeView(APIView):
    def get(self, request, protocol):
        stats = get_protocol_stats(protocol)

        if protocol == "compound":
            d3m = compound.D3MCompoundCompute()
        else:
            d3m = aave.D3MAaveCompute()
        line = d3m.d3m_model.max_debt_ceiling
        bar = d3m.d3m_model.target_borrow_rate

        if "debt_ceiling" in request.GET:
            try:
                debt_ceiling = Decimal(request.GET.get("debt_ceiling"))
            except ValueError:
                return Response(None, status.HTTP_400_BAD_REQUEST)
        else:
            debt_ceiling = line

        if "target_borrow_rate" in request.GET:
            try:
                target_borrow_rate = (
                    Decimal(request.GET.get("target_borrow_rate")) / 100
                )
            except ValueError:
                return Response(None, status.HTTP_400_BAD_REQUEST)
        else:
            target_borrow_rate = bar

        data = d3m.compute_metrics(target_borrow_rate, debt_ceiling)
        data["line"] = line
        data["bar"] = bar

        result = {"stats": stats, "result": data}
        return Response(result, status.HTTP_200_OK)


class D3MDaiBorrowCurveView(APIView):
    def get(self, request, protocol):
        if protocol == "compound":
            d3m = compound.D3MCompoundCompute()
        else:
            d3m = aave.D3MAaveCompute()
        return Response(d3m.dai_curve, status.HTTP_200_OK)
