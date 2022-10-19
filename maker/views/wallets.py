# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Vault, VaultEventState, VaultOwner


class WalletView(APIView):
    def get(self, request, address):
        owner = get_object_or_404(VaultOwner, address=address)
        all_vaults = self.request.GET.get("all_vaults")
        filters = {}
        if all_vaults != "1":
            filters["is_active"] = True

        vaults = Vault.objects.filter(owner_address=owner.address, **filters).values(
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
            "osm_price",
        )

        data = {
            "vaults": vaults,
            "name": owner.name,
            "ens": owner.ens,
            "address": owner.address,
        }
        return Response(data, status.HTTP_200_OK)


class WalletDebtHistoryView(APIView):
    def get(self, request, address):
        owner = get_object_or_404(VaultOwner, address=address)
        all_vaults = self.request.GET.get("all_vaults")
        filters = {}
        if all_vaults != "1":
            filters["is_active"] = True

        vault_uids = list(
            Vault.objects.filter(owner_address=owner.address, **filters).values_list(
                "uid", flat=True
            )
        )

        debts = (
            VaultEventState.objects.filter(vault_uid__in=vault_uids)
            .values("vault_uid", "after_principal", "timestamp")
            .order_by("timestamp")
        )

        return Response(debts, status.HTTP_200_OK)
