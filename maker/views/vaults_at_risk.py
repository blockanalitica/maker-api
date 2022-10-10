# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.db.models.aggregates import Count, Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Vault

from ..modules.vaults_at_risk import get_vaults_at_risk, get_vaults_at_risk_market


class VaultsAtRiskView(APIView):
    """
    Get vaults at risk
    """

    def get(self, request):
        data = get_vaults_at_risk()
        return Response(data, status.HTTP_200_OK)


class VaultsAtRiskMarketView(APIView):
    """
    Get vaults at risk market
    """

    def get(self, request):
        data = get_vaults_at_risk_market()
        return Response(data, status.HTTP_200_OK)


class VaultsAtRiskCountView(APIView):
    def get(self, request):
        at_risk = Vault.objects.filter(is_at_risk=True, is_active=True).aggregate(
            count=Count("id"), debt=Sum("debt")
        )
        return Response(at_risk, status.HTTP_200_OK)
