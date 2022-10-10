# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.db.models.aggregates import Count, Sum
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Ilk, MakerWalletOwner, Vault


class WhalesView(APIView):
    """
    Get whales
    """

    def get(self, request):
        total_risky_debt = Ilk.objects.filter(
            is_active=True, type__in=["lp", "asset"], is_stable=False
        ).aggregate(Sum("dai_debt"))["dai_debt__sum"]
        results = []
        for whale in MakerWalletOwner.objects.filter(is_whale=True):
            wallet_addresss = whale.wallets.values_list("address", flat=True)
            data = Vault.objects.filter(
                owner_address__in=wallet_addresss, is_active=True
            ).aggregate(number_of_vaults=Count("id"), total_debt=Sum("debt"))
            collateral_symbols = Vault.objects.filter(
                owner_address__in=wallet_addresss, is_active=True
            ).values_list("collateral_symbol", flat=True)
            if data["number_of_vaults"] == 0:
                continue
            results.append(
                {
                    "name": whale.name,
                    "slug": whale.slug,
                    "number_of_vaults": data["number_of_vaults"],
                    "total_debt": data["total_debt"],
                    "share": data["total_debt"] / total_risky_debt,
                    "collateral_symbols": set(collateral_symbols),
                }
            )

        data = {"results": results}
        return Response(data, status.HTTP_200_OK)


class WhaleView(APIView):
    """
    Get whale
    """

    def get(self, request, slug):
        owner = MakerWalletOwner.objects.get(slug=slug)
        wallet_addresss = owner.wallets.values_list("address", flat=True)
        vaults = Vault.objects.filter(
            owner_address__in=wallet_addresss, is_active=True
        ).values(
            "uid",
            "ilk",
            "collateral_symbol",
            "owner_address",
            "owner_name",
            "collateral",
            "debt",
            "collateralization",
            "liquidation_price",
            "protection_score",
            "liquidation_drop",
            "last_activity",
            "protection_service",
        )

        data = {"results": vaults, "name": owner.name}
        return Response(data, status.HTTP_200_OK)
