# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta
from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import GasPrice

from ..modules.risk import get_liquidation_curve_for_all, get_overall_stats
from ..modules.risk_premium import (
    get_capital_at_risk_history_ilks,
    get_capital_at_risk_history_overall,
    get_risky_debt_history,
)


class LiquidationCurveView(APIView):
    """
    Get liquidatin curve for all ilks
    """

    def get(self, request):
        type = request.GET.get("type", "total")
        data = get_liquidation_curve_for_all(type=type)
        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class MakerStatsView(APIView):
    """
    Get maker stats
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 30))
        data = get_overall_stats(days_ago)
        return Response(data, status.HTTP_200_OK)


class CapitalAtRiskOverallView(APIView):
    """
    Get capital at risk history
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 30))
        data = get_capital_at_risk_history_overall(days_ago)
        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class CapitalAtRiskOverallIlkView(APIView):
    """
    Get capital at risk history per ilk
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 30))
        data = get_capital_at_risk_history_ilks(days_ago)
        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class PercentOfRiskyDebtView(APIView):
    """
    Get risky debt
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 30))
        data = get_risky_debt_history(days_ago)
        response = {"results": data}
        return Response(response, status.HTTP_200_OK)


class GasView(APIView):
    """
    Get gas cost data
    """

    def get(self, request):
        days_ago = int(request.GET.get("days_ago", 1))
        timestamp = (datetime.now() - timedelta(days=int(days_ago))).timestamp()
        gas_price = GasPrice.objects.latest()
        try:
            previous_gas_price = GasPrice.objects.filter(
                timestamp__lte=timestamp
            ).latest()
        except GasPrice.DoesNotExist:
            previous_gas_price = None
        actions = [
            {"name": "ETH transfer", "gas": 21000},
            {"name": "DAI transfer", "gas": 50000},
            {"name": "Create DS Proxy", "gas": 600000},
            {"name": "Open Vault and Mint", "gas": 500000},
            {"name": "Repay and Close", "gas": 500000},
            {"name": "Vault Maintenance", "gas": 700000},
            {"name": "Auction Kick", "gas": 450000},
            {"name": "Auction Take", "gas": 180000},
        ]

        gwei = Decimal(gas_price.rapid / 1000000000)

        eth_price_gwei = gas_price.eth_price / 1000000000

        gas = {"fast": gwei, "fast_usd": gwei * eth_price_gwei}

        if previous_gas_price:
            previous_gwei = Decimal(previous_gas_price.rapid / 1000000000)
            gas["previous_fast"] = previous_gwei
            gas["fast_diff"] = gwei - previous_gwei
            previous_eth_price_gwei = previous_gas_price.eth_price / 1000000000

        actions_gas = []
        for action in actions:
            fast_price = action["gas"] * gwei * eth_price_gwei
            action["fast_price"] = fast_price

            if previous_gas_price:
                previous_fast_price = (
                    action["gas"] * previous_gwei * previous_eth_price_gwei
                )
                action["previous_fast_price"] = previous_fast_price
                action["fast_price_diff"] = fast_price - previous_fast_price
            actions_gas.append(action)

        data = {
            "gas": gas,
            "actions": actions_gas,
        }
        return Response(data, status.HTTP_200_OK)
