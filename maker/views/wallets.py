# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Vault, VaultEventState, VaultOwner
from maker.utils.views import PaginatedApiView, fetch_all


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
        sql = """
            SELECT
                  a.timestamp
                , b.vault_uid
                , b.ilk
                , c.after_principal
            FROM (
                SELECT
                    DISTINCT(timestamp)
                FROM maker_vaulteventstate
                WHERE vault_uid IN %s
            ) a
            CROSS JOIN (
                SELECT DISTINCT(vault_uid), ilk
                FROM maker_vaulteventstate
                WHERE vault_uid IN %s
            ) b
            LEFT JOIN LATERAL (
                SELECT after_principal
                FROM maker_vaulteventstate x
                WHERE x.timestamp <= a.timestamp
                AND x.vault_uid = b.vault_uid
                ORDER BY x.timestamp DESC
                LIMIT 1
            ) c
            ON 1=1
            ORDER BY a.timestamp
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [tuple(vault_uids), tuple(vault_uids)])
            data = fetch_all(cursor)

        return Response(data, status.HTTP_200_OK)


class WalletEventsView(PaginatedApiView):
    default_order = "-datetime"
    ordering_fields = [
        "datetime",
    ]

    def get_queryset(self, **kwargs):
        owner = get_object_or_404(VaultOwner, address=kwargs["address"])
        all_vaults = self.request.GET.get("all_vaults")
        filters = {}
        if all_vaults != "1":
            filters["is_active"] = True

        vault_uids = list(
            Vault.objects.filter(owner_address=owner.address, **filters).values_list(
                "uid", flat=True
            )
        )
        return VaultEventState.objects.filter(vault_uid__in=vault_uids).values(
            "datetime",
            "operation",
            "human_operation",
            "block_number",
            "collateral",
            "principal",
            "before_ratio",
            "after_ratio",
            "osm_price",
            "vault_uid",
            "ilk",
        )
