# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.db.models.aggregates import Count, Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Ilk, Vault, VaultOwnerGroup


class WhalesView(APIView):
    """
    Get whales
    """

    def get(self, request):
        total_risky_debt = Ilk.objects.filter(
            is_active=True, type__in=["lp", "asset"], is_stable=False
        ).aggregate(Sum("dai_debt"))["dai_debt__sum"]
        results = []

        for group in VaultOwnerGroup.objects.filter(tags__contains=["whale"]):
            addresses = group.addresses.all().values_list("address", flat=True)
            data = Vault.objects.filter(
                owner_address__in=addresses, is_active=True
            ).aggregate(number_of_vaults=Count("id"), total_debt=Sum("debt"))

            collateral_symbols = Vault.objects.filter(
                owner_address__in=addresses, is_active=True
            ).values_list("collateral_symbol", flat=True)

            if data["number_of_vaults"] == 0:
                continue

            results.append(
                {
                    "name": group.name,
                    "slug": group.slug,
                    "number_of_vaults": data["number_of_vaults"],
                    "total_debt": data["total_debt"],
                    "share": data["total_debt"] / total_risky_debt,
                    "collateral_symbols": set(collateral_symbols),
                }
            )

        data = {"results": results}
        return Response(data, status.HTTP_200_OK)
