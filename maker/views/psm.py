# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import serpy
from django.db.models import F, Sum, Value
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Asset, Ilk, RawEvent
from maker.utils.views import PaginatedApiView


class PSMEventsSerializer(serpy.DictSerializer):
    block_number = serpy.Field()
    datetime = serpy.Field()
    tx_hash = serpy.Field()
    operation = serpy.Field()
    collateral = serpy.Field()
    principal = serpy.Field()

    symbol = serpy.MethodField()

    def get_symbol(self, obj):
        return obj["ilk"].split("-")[1]


class PSMEventsView(PaginatedApiView):
    """
    Get all events for psm
    """

    default_order = "-block_number"
    ordering_fields = ["block_number", "collateral", "principal", "datetime"]
    serializer_class = PSMEventsSerializer

    def get_queryset(self, search_filters, query_params, **kwargs):
        return RawEvent.objects.filter(
            ilk=kwargs["ilk"], operation__in=["PAYBACK", "GENERATE"]
        ).values(
            "block_number",
            "datetime",
            "tx_hash",
            "operation",
            "collateral",
            "principal",
            "ilk",
        )


class PSMsView(APIView):
    """
    PSMs
    """

    def get(self, request):
        total_debt = Ilk.objects.filter(is_active=True).aggregate(
            total_debt=Sum("dai_debt")
        )["total_debt"]
        data = (
            Ilk.objects.filter(type="psm")
            .annotate(
                share=F("dai_debt") / Value(total_debt),
                utilization=F("dai_debt") / F("dc_iam_line"),
            )
            .values(
                "ilk",
                "dai_debt",
                "collateral",
                "name",
                "share",
                "dc_iam_line",
                "utilization",
            )
        )
        for entry in data:
            symbol = entry["collateral"]
            if symbol == "PAX":
                symbol = "USDP"
            market_cap = Asset.objects.get(symbol=symbol).market_cap
            share_captured = entry["dai_debt"] / market_cap
            entry["share_captured"] = share_captured
        response = {"results": data}
        return Response(response, status.HTTP_200_OK)
