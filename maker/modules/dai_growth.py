# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from decimal import Decimal

import numpy as np
from django.db import connection, transaction
from django.db.models import Sum

from maker.models import MonthlyDaiSupply, PeriodicalDaiSupplyGrowth
from maker.sources.dicu import MCDSnowflake
from maker.utils.views import fetch_all

ILKS = [
    "ETH-A",
    "ETH-B",
    "ETH-C",
    "LINK-A",
    "MATIC-A",
    "RENBTC-A",
    "UNI-A",
    "UNIV2UNIETH-A",
    "UNIV2WBTCDAI-A",
    "UNIV2WBTCETH-A",
    "WBTC-A",
    "WBTC-B",
    "WBTC-C",
    "WSTETH-A",
    "YFI-A",
]


MAIN_ILKS = [
    "ETH-A",
    "ETH-B",
    "ETH-C",
    "WBTC-A",
    "WBTC-B",
    "LINK-A",
    "YFI-A",
    "WSTETH-A",
]


COUNTERPARTY_ILKS = [
    "USDC-A",
    "WBTC-A",
    "WBTC-B",
    "WBTC-C",
    "TUSD-A",
    "USDC-B",
    "USDT-A",
    "PAXUSD-A",
    "GUSD-A",
    "PSM-USDC-A",
    "RENBTC-A",
    "UNIV2WBTCETH-A",
    "UNIV2USDCETH-A",
    "UNIV2ETHUSDT-A",
    "UNIV2WBTCDAI-A",
    "UNIV2DAIUSDT-A",
    "GUNIV3DAIUSDC1-A",
    "PSM-PAX-A",
    "WSTETH-A",
]


def _calculate_gini_coefficient(values):
    array = np.array(values)
    if np.amin(array) < 0:
        array -= np.amin(array)
    array = np.sort(array)
    n = array.size
    index = np.arange(1, n + 1)
    return (np.sum((2 * index - n - 1) * array)) / (n * np.sum(array))


def sync_monthly_dai_supply():
    ilks = ILKS + COUNTERPARTY_ILKS

    try:
        last_dai_supply = MonthlyDaiSupply.objects.latest()
        last_report_date = last_dai_supply.report_date
        from_report_date = last_report_date.strftime("%Y-%m-%d")
    except MonthlyDaiSupply.DoesNotExist:
        from_report_date = "2020-11-01"

    snowflake = MCDSnowflake()
    query = snowflake.run_query(
        """
            with
              vaults as (
                  select
                    vault
                    , min(date_trunc('month', timestamp)) as cohort_date
                  from
                    "MCD_VAULTS"."PUBLIC"."VAULTS"
                  group by 1
                  order by 2 asc),
              report_dates as (
                select
                  distinct
                  date_trunc(month, timestamp) as report_date
                from
                    "MCD_VAULTS"."PUBLIC"."VAULTS"
                where
                    date_trunc(month, timestamp) < date_trunc(
                        'month', CONVERT_TIMEZONE('UTC', current_timestamp))
                order by 1
              ),
              vault_events_cum as (
              select
                  vault
                  , ilk
                  , cohort_date
                  , date_trunc('day', timestamp) as operation_date
                  , timestamp
                  , sum(dprincipal) over (
                        partition by vault order by timestamp asc) as dprincipal_cum
                  , sum(dfees) over (
                        partition by vault order by timestamp asc) as dfees_cum
              from
                  vaults a
              join
                  "MCD_VAULTS"."PUBLIC"."VAULTS" b
              using
                  (vault)
              order by
                  timestamp asc),

            vault_events_cum_report_date as (
            select
                a.report_date
                , b.*
            from
                report_dates a
            left join
                vault_events_cum b
            on
                (a.report_date >= b.cohort_date)
                and (b.operation_date < a.report_date + interval '1 month')
            ),
            vault_events_cum_report_date_last as (
            select
                  distinct
                  vault
                  , ilk
                  , report_date
                  , cohort_date
                  , last_value(dprincipal_cum) over (
                        partition by vault, report_date order by timestamp
                        ) as last_dprincipal_cum
                  , last_value(dfees_cum) over (
                        partition by vault, report_date order by timestamp
                        ) as last_dfees_cum
            from
                vault_events_cum_report_date
            ),
            final as (
              select
                  report_date
                  , cohort_date
                  , ilk
                  , vault
                  , datediff(month, cohort_date, report_date) + 1 as tenure
                  , sum(last_dprincipal_cum - last_dfees_cum) as total_dai_supply
              from
                  vault_events_cum_report_date_last
              where
                  ilk in ({})
              group by 1,2,3,4
              order by 1,2
            )
            select
                *
                , decode(tenure = 1, true, 'New', 'Retained') as tenure_category
            from
                final
            where
                total_dai_supply > 0
            and
              report_date > '{}'
            """.format(
            ", ".join(["'{}'".format(ilk) for ilk in ilks]), from_report_date
        )
    )

    bulk_create = []
    data = query.fetchmany(size=1000)
    while len(data) > 0:
        for row in data:
            bulk_create.append(
                MonthlyDaiSupply(
                    report_date=row[0],
                    cohort_date=row[1],
                    ilk=row[2],
                    vault_uid=row[3],
                    tenure=row[4],
                    dai_supply=Decimal(str(row[5])),
                    tenure_category=row[6],
                )
            )
            if len(bulk_create) == 500:
                MonthlyDaiSupply.objects.bulk_create(bulk_create)
                bulk_create = []

        data = query.fetchmany(size=1000)

    if bulk_create:
        MonthlyDaiSupply.objects.bulk_create(bulk_create)

    snowflake.close()


def _categorize_cp_risk_source(ilk):
    if ilk in {"WBTC-A", "UNIV2WBTCETH-A", "UNIV2WBTCDAI-A", "WBTC-B", "WBTC-C"}:
        return "BitGo"
    elif ilk in {"GUNIV3DAIUSDC1-A"}:
        return "Gemini and Circle"
    elif ilk in {"USDC-A", "USDC-B", "PSM-USDC-A", "UNIV2USDCETH-A"}:
        return "Circle"
    elif ilk in {"USDT-A", "UNIV2ETHUSDT-A", "UNIV2DAIUSDT-A"}:
        return "Tether"
    elif ilk in {"PAXUSD-A", "PSM-PAX-A"}:
        return "Paxos"
    elif ilk == "GUSD-A":
        return "Gemini"
    elif ilk == "RENBTC-A":
        return "Ren"
    elif ilk == "WSTETH-A":
        return "Lido"
    elif ilk == "TUSD-A":
        return "TrustToken"
    return "Unknown"


class DAISupplyRiskModule:
    def ilk_supply(self):
        if self._ilk_supply is None:
            dai_supplies = (
                MonthlyDaiSupply.objects.filter(ilk__in=ILKS)
                .values(
                    "report_date",
                    "ilk",
                )
                .annotate(dai_supply=Sum("dai_supply"))
                .order_by("ilk", "report_date")
            )

            self._ilk_supply = dai_supplies
        return self._ilk_supply

    def vault_type_data(self):
        rows = (
            MonthlyDaiSupply.objects.filter(ilk__in=ILKS)
            .values(
                "report_date",
                "ilk",
            )
            .annotate(dai_supply=Sum("dai_supply"))
            .order_by("ilk", "report_date")
        )

        sql = """
        SELECT DISTINCT ON (symbol, report_date)
              date_trunc('month', datetime) as report_date
            , symbol
            , first_value(current_price) OVER w as open_price
            , last_value(current_price) OVER w as close_price
        FROM maker_osm
        WHERE symbol IN %s
        WINDOW w AS (
            PARTITION BY symbol, date_trunc('month', datetime)
            ORDER BY datetime RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        )
        """
        assets = set(
            [ilk.replace("-A", "").replace("-B", "").replace("-C", "") for ilk in ILKS]
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, [tuple(assets)])
            osm_query = fetch_all(cursor)

        osms = defaultdict(lambda: defaultdict(dict))
        for osm in osm_query:
            osms[osm["symbol"]][osm["report_date"].date()] = {
                "open_price": osm["open_price"],
                "close_price": osm["close_price"],
            }

        data = []
        prev = rows[0]
        for row in rows[1:]:
            if row["ilk"] != prev["ilk"]:
                prev = row
                # Skip the first record of a new ILK, otherwise we'll incorectly
                # calculate differences between dates for specific ILK
                continue

            row["dai_supply_delta_abs"] = row["dai_supply"] - prev["dai_supply"]

            dai_supply_multiplier = round(row["dai_supply"] / prev["dai_supply"], 2)

            asset = row["ilk"].replace("-A", "").replace("-B", "").replace("-C", "")

            osm = osms[asset][row["report_date"]]
            if osm:
                if osm["open_price"] == 0:
                    continue

                row["dai_supply_organic_demand_growth_perc"] = round(
                    (
                        (
                            dai_supply_multiplier
                            / round(
                                osm["close_price"] / osm["open_price"],
                                2,
                            )
                        )
                        - 1
                    )
                    * 100,
                    2,
                )

            data.append(row)
            prev = row

        return data

    def tenure_category_data(self):
        rows = (
            MonthlyDaiSupply.objects.filter(ilk__in=ILKS)
            .values(
                "report_date",
                "tenure_category",
            )
            .annotate(dai_supply=Sum("dai_supply"))
            .order_by("tenure_category", "report_date")
        )
        return rows

    def new_supply_per_vault_type_data(self):
        rows = (
            MonthlyDaiSupply.objects.filter(ilk__in=ILKS, tenure_category="New")
            .values(
                "report_date",
                "ilk",
            )
            .annotate(dai_supply=Sum("dai_supply"))
            .order_by("ilk", "report_date")
        )
        data = []
        grouped = defaultdict(Decimal)
        for row in rows:
            if row["ilk"] not in MAIN_ILKS:
                grouped[row["report_date"]] += row["dai_supply"]
            else:
                data.append(row)

        for report_date, value in grouped.items():
            data.append(
                {
                    "ilk": "Other",
                    "report_date": report_date,
                    "dai_supply": value,
                }
            )

        return data

    def cohort_data(self):
        rows = (
            MonthlyDaiSupply.objects.filter(ilk__in=ILKS)
            .values(
                "cohort_date",
                "report_date",
            )
            .annotate(dai_supply=Sum("dai_supply"))
            .order_by("report_date", "cohort_date")
        )
        return rows

    def concentration_risk_whales_data(self):
        # Whale 1 - Nexo
        # Whale 2 - Celsius
        # Whale 3 - 7 Siblings
        whales = {
            "8463": "Whale 1",
            "9167": "Whale 1",
            "26180": "Whale 1",
            "25977": "Whale 2",
            "24622": "Whale 2",
            "24620": "Whale 2",
            "24603": "Whale 2",
            "2527": "Whale 3",
            "15990": "Whale 3",
            "7855": "Whale 3",
            "2686": "Whale 3",
            "3241": "Whale 3",
            "2557": "Whale 3",
            "1154": "Whale 3",
        }
        rows = MonthlyDaiSupply.objects.filter(ilk__in=ILKS, dai_supply__gt=100).values(
            "report_date", "vault_uid", "dai_supply"
        )

        print(len(rows))

        total_supply = defaultdict(Decimal)
        groups = defaultdict(lambda: defaultdict(Decimal))

        for row in rows:
            key = whales.get(row["vault_uid"], "Other")
            groups[row["report_date"]][key] += row["dai_supply"]
            total_supply[row["report_date"]] += row["dai_supply"]

        data = []
        for report_date, month_data in groups.items():
            for key, value in month_data.items():
                data.append(
                    {
                        "report_date": report_date,
                        "whale": key,
                        "dai_supply_percent": round(
                            value / total_supply[report_date], 4
                        ),
                    }
                )

        return data

    def gini_data(self):
        rows = (
            MonthlyDaiSupply.objects.filter(ilk__in=ILKS, dai_supply__gt=100)
            .values(
                "report_date",
                "ilk",
                "dai_supply",
            )
            .order_by("ilk", "report_date")
        )

        data = []
        supplies = []
        prev = rows[0]
        for row in rows[1:]:
            if prev["ilk"] != row["ilk"] or prev["report_date"] != row["report_date"]:
                gini = round(_calculate_gini_coefficient(supplies), 2)
                data.append(
                    {
                        "ilk": prev["ilk"],
                        "report_date": prev["report_date"],
                        "gini": gini,
                    }
                )
                supplies = []

            supplies.append(row["dai_supply"])
            prev = row

        gini = round(_calculate_gini_coefficient(supplies), 2)
        data.append(
            {
                "ilk": prev["ilk"],
                "date": prev["report_date"],
                "gini": gini,
            }
        )

        return data

    def counterparties_data(self):
        rows = (
            MonthlyDaiSupply.objects.filter(ilk__in=COUNTERPARTY_ILKS)
            .values("report_date", "ilk")
            .annotate(dai_supply=Sum("dai_supply"))
            .order_by("report_date", "ilk")
        )

        grouped = defaultdict(lambda: defaultdict(Decimal))
        for row in rows:
            category = _categorize_cp_risk_source(row["ilk"])
            de = row["dai_supply"]
            if "UNIV" in row["ilk"]:
                de = row["dai_supply"] // 2
            grouped[row["report_date"]][category] += de

        data = []
        for report_date, group in grouped.items():
            for key, value in group.items():
                data.append(
                    {
                        "counterparty": key,
                        "report_date": report_date,
                        "debt_exposure": value,
                    }
                )
        return data

    def dai_supply_growth_periodical_data(self):
        debt_weighted_groups = defaultdict(Decimal)
        debt_time_groups = defaultdict(list)

        rows = PeriodicalDaiSupplyGrowth.objects.all().order_by("time_period")
        for row in rows:
            debt_weighted_groups[
                row.time_period
            ] += row.debt_weighted_demand_growth_perc
            debt_time_groups[row.time_period].append(
                {"key": row.ilk, "value": row.demand_growth}
            )

        debt_weighted = []
        for key, value in debt_weighted_groups.items():
            debt_weighted.append({"key": key, "value": value})

        return debt_weighted, debt_time_groups


def sync_dai_supply_growth_periodical():
    snowflake = MCDSnowflake()
    query = snowflake.run_query(
        """
        with
            osm_prices as (
        select
            *
        from
        (
        select
            distinct
            '7d' as time_period
            , token as collateral_asset
            , last_value(osm_price) over (
                  partition by token order by block
                  ) / first_value(osm_price) over (
                  partition by token order by block
                  )  as price_multiplier
        from
            "MCD_VAULTS"."PUBLIC"."OSM_PRICES"
        where
            time::date >= current_date - 7
        order by 1,2)
        union all
        (
        select
            distinct
            '30d' as time_period
            , token as collateral_asset
            , last_value(osm_price) over (
                  partition by token order by block
                  ) / first_value(osm_price) over (
                  partition by token order by block
                  ) as price_multiplier
        from
            "MCD_VAULTS"."PUBLIC"."OSM_PRICES"
        where
            time::date >= current_date - 30
        order by 1,2)
        union all
        (
        select
            distinct
            '90d' as time_period
            , token as collateral_asset
            , last_value(osm_price) over (
                  partition by token order by block
                  )  / first_value(osm_price) over (
                  partition by token order by block
                  ) as price_multiplier
        from
            "MCD_VAULTS"."PUBLIC"."OSM_PRICES"
        where
            time::date >= current_date - 90
        order by 1,2)),
            dai_supply as
        (
        with
        dai_supply_inner as
        (
        select
            distinct
            date_trunc('day', timestamp) as report_date
            , ilk as vault_type
            , replace(replace(replace(ilk, '-A'),'-B'), '-C') as collateral_asset
            , sum(dprincipal) over (partition by ilk order by date_trunc('day', timestamp)) - sum(dfees) over (partition by ilk order by date_trunc('day', timestamp)) as total_dai_supply
        from
            "MCD_VAULTS"."PUBLIC"."VAULTS"
        where
            ilk not in ('SAI', 'PAXUSD-A', 'TUSD-A', 'USDC-A', 'USDC-B', 'USDT-A', 'GUSD-A', 'UNIV2AAVEETH-A', 'MANA-A', 'COMP-A', 'ZRX-A', 'AAVE-A', 'BAL-A', 'UNIV2DAIUSDC-A', 'KNC-A', 'UNIV2ETHUSDT-A', 'UNIV2DAIUSDT-A', 'UNIV2LINKETH-A', 'UNIV2DAIETH-A',  'UNIV2USDCETH-A', 'BAT-A', 'DIRECT-AAVEV2-DAI', 'LRC-A', 'GUNIV3DAIUSDC1-A', 'GUNIV3DAIUSDC2-A')
        and
            ilk not ilike 'RWA%'
        and
            ilk not ilike 'PSM%'
        order by 1 desc)
        select
            *
        from
        (
        select
             distinct
            '7d' as time_period
            , vault_type
            , collateral_asset
            , first_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as first_dai_supply
            , last_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as last_dai_supply
             , last_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) /  first_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as dai_supply_multiplier
        from
            dai_supply_inner
        where
          report_date >= current_date - 7)
        union all
        (
        select
             distinct
            '30d' as time_period
            , vault_type
            , collateral_asset
            , first_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as first_dai_supply
            , last_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as last_dai_supply
             , last_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) /  first_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as dai_supply_multiplier
        from
            dai_supply_inner
        where
          report_date >= current_date - 30)
        union all
        (
        select
             distinct
            '90d' as time_period
            , vault_type
            , collateral_asset
            , first_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as first_dai_supply
            , last_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as last_dai_supply
             , last_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) /  first_value(total_dai_supply) over (
                  partition by vault_type order by report_date
                  ) as dai_supply_multiplier
        from
            dai_supply_inner
        where
          report_date >= current_date - 90))

        select
              time_period
            , vault_type
            , collateral_asset
            , first_dai_supply
            , last_dai_supply
            , dai_supply_multiplier
            , (dai_supply_multiplier / price_multiplier) * 100 - 100 as organic_demand_growth
        from
            dai_supply
        left join
            osm_prices
        using
            (time_period, collateral_asset)

        WHERE first_dai_supply > 1000000
        """  # noqa: E501
    )

    data = query.fetchall()
    total_dai_supply_period = defaultdict(float)
    for row in data:
        total_dai_supply_period[row[0]] += row[4]

    to_insert = []
    for row in data:
        demand_growth = row[6] or 0
        dai_supply_weight = row[4] / total_dai_supply_period[row[0]]
        organic_debt_weighted_demand_growth_perc = demand_growth * dai_supply_weight
        to_insert.append(
            PeriodicalDaiSupplyGrowth(
                time_period=row[0],
                ilk=row[1],
                demand_growth=demand_growth,
                debt_weighted_demand_growth_perc=organic_debt_weighted_demand_growth_perc,
            )
        )

    with transaction.atomic():
        # First clear the table
        PeriodicalDaiSupplyGrowth.objects.all().delete()
        # Now repopulate the table with data
        PeriodicalDaiSupplyGrowth.objects.bulk_create(to_insert)
