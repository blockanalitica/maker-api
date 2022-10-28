# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.db.models.aggregates import Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Ilk, Vault, VaultOwnerGroup


class WhalesView(APIView):
    """
    Get whales
    """

    def get(self, request):
        risk_ilks = Ilk.objects.filter(
            is_active=True, type__in=["lp", "asset"], is_stable=False
        ).values_list("ilk", flat=True)
        total_risky_debt = Ilk.objects.filter(
            is_active=True, type__in=["lp", "asset"], is_stable=False
        ).aggregate(Sum("dai_debt"))["dai_debt__sum"]
        results = []

        for group in VaultOwnerGroup.objects.filter(tags__contains=["whale"]):
            addresses = group.addresses.all().values_list("address", flat=True)
            data = Vault.objects.filter(
                owner_address__in=addresses, is_active=True
            ).values("collateral_symbol", "debt", "ilk")

            collateral_symbols = []
            total_debt = 0
            total_risk_debt = 0
            count = 0

            if not data:
                continue

            for vault in data:
                collateral_symbols.append(vault["collateral_symbol"])
                total_debt += vault["debt"]
                if vault["ilk"] in risk_ilks:
                    total_risk_debt += vault["debt"]
                count += 1

            collateral_symbols = Vault.objects.filter(
                owner_address__in=addresses, is_active=True
            ).values_list("collateral_symbol", flat=True)

            results.append(
                {
                    "name": group.name,
                    "slug": group.slug,
                    "number_of_vaults": count,
                    "total_debt": total_debt,
                    "share": total_risk_debt / total_risky_debt,
                    "collateral_symbols": set(collateral_symbols),
                }
            )

        data = {"results": results}
        return Response(data, status.HTTP_200_OK)
