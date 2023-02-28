# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

import serpy
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import (
    OSM,
    Ilk,
    IlkHistoricParams,
    Vault,
    VaultEventState,
    VaultProtectionScore,
)
from maker.utils.views import PaginatedApiView


class TimestampToDatetimeField(serpy.Field):
    def to_value(self, value):
        if not value:
            return value
        return datetime.fromtimestamp(value)


class VaultPositionsViewSerializer(serpy.DictSerializer):
    ilk = serpy.StrField(required=False)
    collateral = serpy.Field()
    debt = serpy.Field()
    uid = serpy.StrField()
    collateralization = serpy.Field()
    liquidation_price = serpy.Field()
    liquidation_drop = serpy.Field()
    protection_score = serpy.StrField()
    owner_address = serpy.Field()
    owner_ens = serpy.Field()
    owner_name = serpy.Field()
    osm_price = serpy.Field()
    collateral_change_1d = serpy.Field()
    collateral_change_7d = serpy.Field()
    collateral_change_30d = serpy.Field()
    principal_change_1d = serpy.Field()
    principal_change_7d = serpy.Field()
    principal_change_30d = serpy.Field()
    last_activity = serpy.Field()
    protection_service = serpy.Field()
    ds_proxy_address = serpy.Field()
    ds_proxy_name = serpy.Field()


class VaultEventsViewViewSerializer(serpy.DictSerializer):
    timestamp = TimestampToDatetimeField()
    operation = serpy.Field()
    human_operation = serpy.Field()
    block_number = serpy.Field()
    collateral = serpy.Field()
    principal = serpy.Field()
    before_ratio = serpy.Field()
    after_ratio = serpy.Field()
    osm_price = serpy.Field()
    tx_hash = serpy.Field()


class VaultView(APIView):
    def get(self, request, ilk, uid):
        vault = get_object_or_404(Vault, uid=uid, ilk=ilk)
        data = {
            "ilk": vault.ilk,
            "collateral": vault.collateral,
            "debt": vault.debt,
            "collateralization": vault.collateralization,
            "liquidation_price": vault.liquidation_price,
            "owner_address": vault.owner_address,
            "owner_name": vault.owner_name,
            "owner_ens": vault.owner_ens,
            "ds_proxy_address": vault.ds_proxy_address,
            "ds_proxy_name": vault.ds_proxy_name,
            "protection_service": vault.protection_service,
            "protection_score": vault.protection_score,
            "symbol": (vault.ilk).split("-")[0],
        }
        return Response(data, status.HTTP_200_OK)


class VaultEventsView(PaginatedApiView):
    default_order = "-timestamp"
    ordering_fields = [
        "timestamp",
    ]
    serializer_class = VaultEventsViewViewSerializer
    lookup_field = "uid"

    def get_queryset(self, **kwargs):
        return VaultEventState.objects.filter(
            vault_uid=kwargs["uid"], ilk=kwargs["ilk"]
        ).values(
            "timestamp",
            "operation",
            "human_operation",
            "block_number",
            "collateral",
            "principal",
            "before_ratio",
            "after_ratio",
            "osm_price",
            "tx_hash",
        )


class VaultPositionsView(PaginatedApiView):
    default_order = "-debt"
    ordering_fields = [
        "collateral",
        "debt",
        "collateral_change_1d",
        "collateral_change_7d",
        "collateral_change_30d",
        "principal_change_1d",
        "principal_change_7d",
        "principal_change_30d",
        "last_activity",
        "liquidation_price",
        "liquidation_drop",
        "protection_score",
        "collateralization",
    ]
    serializer_class = VaultPositionsViewSerializer
    lookup_field = "ilk"

    search_fields = [
        "owner_address",
        "uid",
        "owner_name",
        "ds_proxy_address",
    ]

    def get_queryset(self, search_filters, **kwargs):
        type = self.request.GET.get("vaults")
        filter = {}
        if type == "active":
            filter["is_active"] = True
        return Vault.objects.filter(search_filters, ilk=kwargs["ilk"], **filter).values(
            "uid",
            "owner_address",
            "ds_proxy_address",
            "liquidation_price",
            "liquidation_drop",
            "protection_score",
            "collateralization",
            "collateral",
            "debt",
            "collateral_change_1d",
            "collateral_change_7d",
            "collateral_change_30d",
            "principal_change_1d",
            "principal_change_7d",
            "principal_change_30d",
            "osm_price",
            "owner_ens",
            "owner_name",
            "last_activity",
            "protection_service",
            "ds_proxy_name",
        )

    def get_additional_data(self, queryset, **kwargs):
        ilk = get_object_or_404(Ilk, ilk=kwargs["ilk"])
        return {
            "ilk": ilk.ilk,
            "type": ilk.type,
        }


class AllVaultPositionsView(PaginatedApiView):
    default_order = "-debt"
    ordering_fields = [
        "collateral",
        "debt",
        "collateral_change_1d",
        "collateral_change_7d",
        "collateral_change_30d",
        "principal_change_1d",
        "principal_change_7d",
        "principal_change_30d",
        "last_activity",
        "liquidation_drop",
        "protection_score",
        "collateralization",
        "liquidation_price",
    ]
    serializer_class = VaultPositionsViewSerializer

    search_fields = [
        "owner_address",
        "uid",
        "owner_name",
    ]

    def get_queryset(self, search_filters, **kwargs):
        type = self.request.GET.get("vaults")
        filter = {}
        if type == "active":
            filter["is_active"] = True
        return Vault.objects.filter(search_filters, **filter).values(
            "ilk",
            "uid",
            "owner_address",
            "ds_proxy_address",
            "liquidation_price",
            "liquidation_drop",
            "protection_score",
            "collateralization",
            "collateral",
            "debt",
            "collateral_change_1d",
            "collateral_change_7d",
            "collateral_change_30d",
            "principal_change_1d",
            "principal_change_7d",
            "principal_change_30d",
            "osm_price",
            "owner_ens",
            "owner_name",
            "last_activity",
            "protection_service",
            "ds_proxy_name",
        )


class VaultCrHistoryView(APIView):
    def get(self, request, ilk, uid):
        vault = get_object_or_404(Vault, uid=uid, ilk=ilk)
        symbol = vault.ilk.split("-")[0]

        days_ago = int(request.GET.get("days_ago", 7))

        start_cr = (datetime.now() - timedelta(days=days_ago)).timestamp()
        try:
            start_timestamp = (
                VaultEventState.objects.filter(
                    vault_uid=vault.uid, timestamp__lte=start_cr
                )
                .latest()
                .timestamp
            )
        except VaultEventState.DoesNotExist:
            start_timestamp = (
                VaultEventState.objects.filter(vault_uid=vault.uid).earliest().timestamp
            )

        crs = iter(
            VaultEventState.objects.filter(
                vault_uid=vault.uid, timestamp__gte=start_timestamp
            )
            .values("after_collateral", "after_principal", "timestamp")
            .order_by("timestamp")
        )

        data = []

        osms = (
            OSM.objects.filter(timestamp__gte=start_cr, symbol=symbol)
            .values("current_price", "timestamp")
            .order_by("timestamp")
        )
        try:
            start_lr = (
                IlkHistoricParams.objects.filter(
                    ilk=vault.ilk, timestamp__lte=start_cr, type="lr"
                )
                .latest()
                .timestamp
            )
        except IlkHistoricParams.DoesNotExist:
            start_lr = 0

        lrs = iter(
            IlkHistoricParams.objects.filter(
                ilk=vault.ilk, timestamp__gte=start_lr, type="lr"
            )
            .values("timestamp", "lr")
            .order_by("timestamp")
        )

        curr_lr = next(lrs)
        try:
            next_lr = next(lrs)
        except StopIteration:
            next_lr = None

        curr_cr = next(crs)
        try:
            next_cr = next(crs)
        except StopIteration:
            next_cr = None

        cnt = 2
        for osm in osms:
            while next_lr:
                if osm["timestamp"] >= next_lr["timestamp"]:
                    curr_lr = next_lr
                    next_lr = next(lrs, None)
                    cnt += 1
                else:
                    break

            while next_cr:
                if osm["timestamp"] >= next_cr["timestamp"]:
                    curr_cr = next_cr
                    next_cr = next(crs, None)
                else:
                    break

            if curr_cr["after_principal"] > 0:
                cr = round(
                    (
                        (curr_cr["after_collateral"] * osm["current_price"])
                        / (curr_cr["after_principal"] or 1)
                        * 100
                    ),
                    2,
                )
            else:
                cr = 0

            if cnt < 4 and cr > 2000:
                continue

            data.append(
                {
                    "key": "osm_price",
                    "timestamp": osm["timestamp"],
                    "amount": osm["current_price"],
                }
            )
            data.append(
                {
                    "key": "liquidation_ratio",
                    "timestamp": osm["timestamp"],
                    "amount": curr_lr["lr"],
                }
            )
            data.append(
                {
                    "key": "collateralization",
                    "timestamp": osm["timestamp"],
                    "amount": cr,
                }
            )

        events = VaultEventState.objects.filter(
            ilk=ilk, vault_uid=uid, timestamp__gte=start_cr
        ).values(
            "timestamp",
            "human_operation",
        )
        response = {"results": data, "events": events}
        return Response(response, status.HTTP_200_OK)


class VaultsProtectionScoreHistoryView(APIView):
    def get(self, request):
        days_ago = request.GET.get("days_ago")
        ilk = request.GET.get("ilk")
        query_filter = {}
        if ilk:
            uids = Vault.objects.filter(ilk=ilk).values_list("uid", flat=True)
            query_filter["vault_uid__in"] = uids
        if days_ago:
            timestamp = (datetime.now() - timedelta(days=int(days_ago))).timestamp()
            query_filter["timestamp__gte"] = timestamp

        data = (
            VaultProtectionScore.objects.filter(
                **query_filter, protection_score__in=["high", "medium", "low"]
            )
            .order_by("protection_score", "datetime")
            .values("protection_score", "datetime")
            .annotate(amount=Sum("total_debt_dai"))
        )

        return Response(data, status.HTTP_200_OK)


class VaultProtectionScoreMatrix(APIView):
    def get(self, request, ilk, uid):
        protection_scores = VaultProtectionScore.objects.filter(
            vault_uid=uid, ilk=ilk
        ).values("datetime", "protection_score")
        for entry in protection_scores:
            entry["day"] = entry["datetime"].isoweekday()
            entry["datetime"] = entry["datetime"].strftime("%Y-%m-%d")
        if protection_scores.count() == 0:
            protection_scores = "no data"
        return Response(protection_scores, status.HTTP_200_OK)


class VaultDebtHistoryView(APIView):
    def get(self, request, ilk, uid):
        vault = get_object_or_404(Vault, uid=uid, ilk=ilk)
        debts = (
            VaultEventState.objects.filter(vault_uid=vault.uid)
            .values("after_principal", "timestamp")
            .order_by("timestamp")
        )

        events = VaultEventState.objects.filter(ilk=ilk, vault_uid=uid).values(
            "timestamp",
            "human_operation",
        )

        response = {"debts": debts, "events": events}
        return Response(response, status.HTTP_200_OK)
