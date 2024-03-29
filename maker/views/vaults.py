# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta
from decimal import Decimal

import serpy
from django.db.models import Case, F, FloatField, Sum, When
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import (
    OSM,
    Ilk,
    IlkHistoricParams,
    UrnEventState,
    Vault,
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
    datetime = serpy.Field()
    operation = serpy.Field()
    order_index = serpy.Field()
    block_number = serpy.Field()
    collateral = serpy.Field()
    principal = serpy.Field()
    before_ratio = serpy.Field()
    after_ratio = serpy.Field()
    collateral_price = serpy.Field()
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
    default_order = "-order_index"
    ordering_fields = [
        "order_index",
    ]
    serializer_class = VaultEventsViewViewSerializer
    lookup_field = "uid"

    def get_queryset(self, **kwargs):
        vault = get_object_or_404(Vault, uid=kwargs["uid"], ilk=kwargs["ilk"])

        return (
            UrnEventState.objects.filter(urn=vault.urn, ilk=kwargs["ilk"])
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
            )
            .values(
                "datetime",
                "operation",
                "block_number",
                "collateral",
                "principal",
                "order_index",
                "before_ratio",
                "after_ratio",
                "collateral_price",
                "tx_hash",
            )
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
        start_dt = datetime.now() - timedelta(days=days_ago)

        try:
            first_entry_dt = (
                UrnEventState.objects.filter(urn=vault.urn, datetime__lte=start_dt)
                .latest()
                .datetime
            )
            start_timestamp = int(first_entry_dt.timestamp())
        except UrnEventState.DoesNotExist:
            first_entry_dt = (
                UrnEventState.objects.filter(urn=vault.urn).earliest().datetime
            )
            start_timestamp = int(first_entry_dt.timestamp())

        crs = iter(
            UrnEventState.objects.filter(urn=vault.urn, datetime__gte=first_entry_dt)
            .annotate(collateral=F("ink") / 10**18)
            .values("collateral", "debt", "datetime")
            .order_by("datetime")
        )

        data = []

        osms = (
            OSM.objects.filter(timestamp__gte=start_timestamp, symbol=symbol)
            .values("current_price", "timestamp")
            .order_by("timestamp")
        )
        try:
            start_lr = (
                IlkHistoricParams.objects.filter(
                    ilk=vault.ilk, timestamp__lte=start_timestamp, type="lr"
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
                if osm["timestamp"] >= next_cr["datetime"].timestamp():
                    curr_cr = next_cr
                    next_cr = next(crs, None)
                else:
                    break

            if curr_cr["debt"] > 0:
                cr = round(
                    (
                        (curr_cr["collateral"] * osm["current_price"])
                        / (curr_cr["debt"] or 1)
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

        events = (
            UrnEventState.objects.filter(ilk=ilk, urn=vault.urn, datetime__gte=start_dt)
            .annotate(human_operation=F("operation"))
            .values(
                "datetime",
                "human_operation",
            )
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
            UrnEventState.objects.filter(urn=vault.urn, ilk=ilk)
            .values("debt", "datetime")
            .order_by("datetime")
        )

        events = UrnEventState.objects.filter(ilk=ilk, urn=vault.urn).values(
            "datetime",
            "operation",
        )

        response = {"debts": debts, "events": events}
        return Response(response, status.HTTP_200_OK)
