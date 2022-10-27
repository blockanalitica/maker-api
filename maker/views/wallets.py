# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Vault, VaultEventState, VaultOwner, VaultOwnerGroup
from maker.utils.views import PaginatedApiView, fetch_all


class WalletMixin(object):
    def get_base_queryset(self, request, address):
        self.owner = None
        self.owner_group = None
        addresses = []
        if len(address) == 42 and address.startswith("0x"):
            self.owner = get_object_or_404(VaultOwner, address=address)
            addresses = [self.owner.address]
        else:
            self.owner_group = get_object_or_404(VaultOwnerGroup, slug=address)
            addresses = list(
                self.owner_group.addresses.all().values_list("address", flat=True)
            )

        all_vaults = self.request.GET.get("all_vaults")
        filters = {}
        if all_vaults != "1":
            filters["is_active"] = True

        queryset = Vault.objects.filter(owner_address__in=addresses, **filters)
        return queryset


class WalletView(WalletMixin, APIView):
    def get(self, request, address):
        queryset = self.get_base_queryset(request, address)
        vaults = queryset.values(
            "uid",
            "ilk",
            "collateral_symbol",
            "owner_address",
            "owner_name",
            "owner_ens",
            "ds_proxy_address",
            "collateral",
            "debt",
            "collateralization",
            "liquidation_price",
            "protection_score",
            "liquidation_drop",
            "last_activity",
            "protection_service",
            "osm_price",
            "ds_proxy_name",
        )

        if self.owner:
            name = self.owner.name
            ens = self.owner.ens
            owner_address = self.owner.address
            slug = None
        else:
            name = self.owner_group.name
            ens = None
            owner_address = None
            slug = self.owner_group.slug

        data = {
            "vaults": vaults,
            "name": name,
            "ens": ens,
            "address": owner_address,
            "slug": slug,
        }
        return Response(data, status.HTTP_200_OK)


class WalletDebtHistoryView(WalletMixin, APIView):
    def get(self, request, address):
        queryset = self.get_base_queryset(request, address)
        vault_uids = list(queryset.values_list("uid", flat=True))
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
                UNION
                SELECT cast(extract(epoch from current_timestamp) as integer) as timestamp
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


class WalletEventsView(WalletMixin, PaginatedApiView):
    default_order = "-datetime"
    ordering_fields = [
        "datetime",
    ]

    def get_queryset(self, **kwargs):
        queryset = self.get_base_queryset(self.request, kwargs["address"])
        vault_uids = list(queryset.values_list("uid", flat=True))
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
