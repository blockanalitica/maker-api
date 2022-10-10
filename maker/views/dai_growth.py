# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from decimal import Decimal

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..modules.dai_growth import MAIN_ILKS, DAISupplyRiskModule


# Chache for 1 hr
@method_decorator(cache_control(max_age=60 * 60), name="dispatch")
class DaiGrowth(APIView):
    def _group_other(self, vault_type_data):
        data = []
        grouped = defaultdict(lambda: defaultdict(Decimal))
        for row in vault_type_data:
            if row["ilk"] not in MAIN_ILKS:
                grouped[row["report_date"]]["dai_supply"] += row["dai_supply"]
                grouped[row["report_date"]]["dai_supply_delta_abs"] += row[
                    "dai_supply_delta_abs"
                ]
            else:
                data.append(row)

        for report_date, value in grouped.items():
            data.append(
                {
                    "ilk": "Other",
                    "report_date": report_date,
                    "dai_supply": value["dai_supply"],
                    "dai_supply_delta_abs": value["dai_supply_delta_abs"],
                }
            )
        return data

    def get(self, request):
        dai_supply = DAISupplyRiskModule()
        vault_type_data = dai_supply.vault_type_data()
        supply_with_other = self._group_other(vault_type_data)
        debt_weighted, debt_time_groups = dai_supply.dai_supply_growth_periodical_data()
        data = {
            "per_vault_type": supply_with_other,
            "organic_demand_growth_perc": vault_type_data,
            "supply_per_tenure_category": dai_supply.tenure_category_data(),
            "new_supply_per_vault_type": dai_supply.new_supply_per_vault_type_data(),
            "supply_per_cohort": dai_supply.cohort_data(),
            "concentration_risk_whales": dai_supply.concentration_risk_whales_data(),
            "concentration_risk_gini": dai_supply.gini_data(),
            "counterparties": dai_supply.counterparties_data(),
            "organic_supply_debt_weighted": debt_weighted,
            "organic_demand_growth_per_vault_7d": debt_time_groups["7d"],
            "organic_demand_growth_per_vault_30d": debt_time_groups["30d"],
            "organic_demand_growth_per_vault_90d": debt_time_groups["90d"],
        }

        return Response(data, status.HTTP_200_OK)
