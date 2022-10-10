# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

import serpy
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.models import Ilk
from maker.modules.dust import simulate as simulate_dust
from maker.modules.risk_premium import (
    DEFAULT_SCENARIO_PARAMS,
    JUMP_FREQUENCY_LIST,
    JUMP_SEVERITY_LIST,
    KEEPER_PROFIT_LIST,
    compute,
)
from maker.utils.views import PaginatedApiView

from ..models import OSM, Vault


class RiskModel(APIView):
    def get(self, request):
        ilk = (request.GET.get("ilk") or "ETH-A").upper()
        if ilk not in DEFAULT_SCENARIO_PARAMS:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        try:
            jump_frequency = int(
                request.GET.get(
                    "jump_frequency", DEFAULT_SCENARIO_PARAMS[ilk]["jump_frequency"]
                )
            )

            jump_severity = float(
                request.GET.get(
                    "jump_severity", DEFAULT_SCENARIO_PARAMS[ilk]["jump_severity"]
                )
            )

            keeper_profit = float(
                request.GET.get(
                    "keeper_profit", DEFAULT_SCENARIO_PARAMS[ilk]["keeper_profit"]
                )
            )
        except ValueError:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        if (
            jump_severity not in JUMP_SEVERITY_LIST
            or jump_frequency not in JUMP_FREQUENCY_LIST
            or keeper_profit not in KEEPER_PROFIT_LIST
        ):
            return Response(None, status.HTTP_400_BAD_REQUEST)

        data = compute(
            ilk=ilk,
            jump_frequency=jump_frequency,
            jump_severity=jump_severity,
            keeper_profit=keeper_profit,
        )
        data["vault_types"] = list(DEFAULT_SCENARIO_PARAMS)
        data["default_params"] = DEFAULT_SCENARIO_PARAMS[ilk]
        return Response(data, status.HTTP_200_OK)


class VaultAtRiskSerializer(serpy.DictSerializer):
    uid = serpy.Field()
    ilk = serpy.Field()
    collateral_symbol = serpy.Field()
    owner_address = serpy.Field()
    collateral = serpy.Field()
    debt = serpy.Field()
    collateralization = serpy.Field()
    liquidation_price = serpy.Field()
    protection_score = serpy.Field()
    last_activity = serpy.Field()
    owner_name = serpy.Field()
    protection_service = serpy.Field()


class VaultsAtRiskSimulationView(PaginatedApiView):
    serializer_class = VaultAtRiskSerializer
    default_order = "-debt"
    ordering_fields = [
        "ilk",
        "collateralization",
        "liquidation_price",
        "debt",
        "last_activity",
        "owner_address",
    ]

    def get_queryset(self, **kwargs):
        try:
            self.drop = int(self.request.GET.get("drop"))
        except ValueError:
            self.drop = 0.05
        else:
            self.drop = self.drop / 100

        queryset = Vault.objects.filter(liquidation_drop__lte=self.drop, is_active=True)
        return queryset.values(
            "uid",
            "ilk",
            "collateral_symbol",
            "owner_address",
            "collateral",
            "debt",
            "collateralization",
            "liquidation_price",
            "protection_score",
            "last_activity",
            "owner_name",
            "protection_service",
        )

    def get_additional_data(self, queryset, **kwargs):
        aggregate_data = queryset.aggregate(
            total_debt=Sum("debt"),
            high=Sum("debt", filter=Q(protection_score="high")),
            medium=Sum("debt", filter=Q(protection_score="medium")),
            low=Sum("debt", filter=Q(protection_score="low")),
            count=Count("uid"),
        )

        symbols = list(
            queryset.values_list("collateral_symbol", flat=True)
            .distinct("collateral_symbol")
            .order_by("collateral_symbol")
        )

        osm_prices = []
        for symbol in symbols:
            osm = OSM.objects.filter(symbol=symbol).latest()
            next_price = osm.current_price * (Decimal("1") - Decimal(str(self.drop)))
            diff = round(
                ((next_price - osm.current_price) / osm.current_price * 100), 2
            )
            osm_prices.append(
                {
                    "current_price": osm.current_price,
                    "next_price": next_price,
                    "datetime": osm.datetime,
                    "symbol": osm.symbol,
                    "diff": diff,
                }
            )

        return {
            "aggregate_data": aggregate_data,
            "osm_prices": osm_prices,
        }


class DustSimulationView(APIView):
    def get(self, request):
        ilk = (request.GET.get("ilk") or "ETH-A").upper()
        ilk_obj = get_object_or_404(Ilk.objects.active(), ilk=ilk)
        default_settings = {
            "eth_price": float(ilk_obj.osm_price),
            "liquidation_fees": 0.13,
            "bark": 450000.0,
            "take": 180000.0,
            "dex_trade": 300000.0,
            "base_debt": 0,
        }

        try:
            eth_price = float(
                request.GET.get("eth_price", default_settings["eth_price"])
            )
            liquidation_fees = float(
                request.GET.get(
                    "liquidation_fees", default_settings["liquidation_fees"]
                )
            )
            bark = float(request.GET.get("bark", default_settings["bark"]))
            take = float(request.GET.get("take", default_settings["take"]))
            dex_trade = float(
                request.GET.get("dex_trade", default_settings["dex_trade"])
            )
            base_debt = bool(
                int(request.GET.get("base_debt", default_settings["base_debt"]))
            )
        except ValueError:
            return Response(None, status.HTTP_400_BAD_REQUEST)

        sim_data = simulate_dust(
            ilk_obj, base_debt, eth_price, liquidation_fees, bark, take, dex_trade
        )

        ilks = Ilk.objects.active().order_by("ilk").values_list("ilk", flat=True)
        data = {
            "results": sim_data,
            "ilks": list(ilks),
            "default_settings": default_settings,
        }
        return Response(data, status.HTTP_200_OK)
