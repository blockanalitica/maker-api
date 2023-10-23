# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
from decimal import Decimal

from django.db import connection
from django.db.models import Case, F, FloatField, OuterRef, Subquery, When
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import UrnEventState, Vault, VaultOwner, VaultOwnerGroup
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
            "collateral_change_1d",
            "collateral_change_7d",
            "collateral_change_30d",
            "principal_change_1d",
            "principal_change_7d",
            "principal_change_30d",
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
        vault_urns = list(queryset.values_list("urn", flat=True))

        if not vault_urns:
            return Response(None, status.HTTP_200_OK)

        sql = """
            SELECT
                a.timestamp
                , b.uid AS vault_uid
                , b.ilk
                , c.after_principal
            FROM (
                SELECT
                    DISTINCT(datetime) AS timestamp
                    , urn
                FROM maker_urneventstate
                WHERE urn IN %s
                UNION
                SELECT
                    to_timestamp(cast(extract(epoch from current_timestamp) as double precision))
                    AS timestamp
                    , NULL as urn
            ) a
            CROSS JOIN (
                SELECT DISTINCT(uid), ilk, urn  -- Select the urn column here
                FROM maker_vault
                WHERE urn IN %s
            ) b
            LEFT JOIN LATERAL (
                SELECT debt AS after_principal
                FROM maker_urneventstate x
                WHERE x.datetime <= a.timestamp
                AND x.urn = b.urn
                ORDER BY x.datetime DESC
                LIMIT 1
            ) c
            ON 1=1
            ORDER BY a.timestamp
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [tuple(vault_urns), tuple(vault_urns)])
            data = fetch_all(cursor)

        return Response(data, status.HTTP_200_OK)


class WalletEventsView(WalletMixin, PaginatedApiView):
    default_order = "-datetime"
    ordering_fields = [
        "datetime",
    ]

    def get_queryset(self, **kwargs):
        queryset = self.get_base_queryset(self.request, kwargs["address"])
        vault_urns = list(queryset.values_list("urn", flat=True))
        return (
            UrnEventState.objects.filter(urn__in=vault_urns)
            .annotate(
                collateral=F("dink") / Decimal("1e18"),
                principal=F("dart") / Decimal("1e18") * F("rate") / Decimal("1e27"),
                before_ratio=Case(
                    When(
                        debt__gt=(
                            F("dart") / Decimal("1e18") * F("rate") / Decimal("1e27")
                        ),
                        then=(
                            (F("ink") - F("dink"))
                            / Decimal("1e18")
                            * F("collateral_price")
                        )
                        / (
                            F("debt")
                            - (
                                F("dart")
                                / Decimal("1e18")
                                * F("rate")
                                / Decimal("1e27")
                            )
                        )
                        * 100,
                    ),
                    default=0,
                    output_field=FloatField(),
                ),
                after_ratio=Case(
                    When(
                        debt__gt=0,
                        then=(F("ink") / Decimal("1e18") * F("collateral_price"))
                        / F("debt")
                        * 100,
                    ),
                    default=0,
                    output_field=FloatField(),
                ),
                vault_uid=Subquery(
                    Vault.objects.filter(
                        ilk=OuterRef("ilk"), urn=OuterRef("urn")
                    ).values("uid")[:1]
                ),
            )
            .values(
                "datetime",
                "operation",
                "block_number",
                "collateral",
                "principal",
                "before_ratio",
                "after_ratio",
                "collateral_price",
                "vault_uid",
                "ilk",
                "tx_hash",
            )
        )
