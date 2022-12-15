# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from django.db import connection
from django_bulk_load import bulk_update_models

from ..models import Vault, VaultProtectionScore

VAULT_TYPE_TO_VAULT_ASSET_MAPPER = {
    "ETH-A": "ETH",
    "ETH-B": "ETH",
    "ETH-C": "ETH",
    "MATIC-A": "MATIC",
    "LINK-A": "LINK",
    "YFI-A": "YFI",
    "WBTC-A": "WBTC",
    "WBTC-B": "WBTC",
    "WBTC-C": "WBTC",
    "WSTETH-A": "STETH",
    "WSTETH-B": "STETH",
    "RETH-A": "RETH",
}

UNI_LP_VAULT_ASSET_MAP = {
    "UNIV2USDCETH-A": ["USDC", "ETH"],
    "CRVV1ETHSTETH-A": ["STETH", "ETH"],
}


def run_query(sql):
    output_df = pd.read_sql_query(sql, connection)
    return output_df


def get_protection_score_data():

    df_asset_price_drops = run_query(
        """
    -- daily minimum/opening price delta in the last N months (current = 18m)
    with
    osm_prices as
    (
    select
        distinct
        date_trunc('day', datetime) as report_date
        , symbol as collateral_asset
        , first_value(current_price) over (
                partition by date_trunc('day', datetime), symbol order by block_number
                ) as opening_price
            , min(current_price) over (
                partition by date_trunc('day', datetime), symbol order by block_number
                ) as min_price
    from
        maker_osm
    where
        datetime between current_date - interval '18 months' and current_date - 1
    order by 1,2 asc),

    osm_price_delta as (

    select
        *
        , round(((min_price / nullif(opening_price,0)) * 100) - 100,2)
        as price_delta_perc
    from
        osm_prices
    order by 5)

    select
        *
    from
        osm_price_delta
    where
        price_delta_perc < 0

    """
    )

    df_cr_increase_actions = run_query(
        """


    select
        vault_uid as vault
        , a.ilk
        , b.collateral as collateral_asset
        , date_trunc('day', to_timestamp(a.timestamp)) as report_date
        , count(*) as cr_increase_actions
    from
        maker_vaulteventstate a
    join
        maker_ilk b
    on
        a.ilk = b.ilk
    where
        after_ratio > before_ratio
    and
        type in ('asset', 'lp')
    group by 1,2,3,4
    order by 5 desc
    """
    )

    df_annualized_volatility = run_query(
        """
    with
        osm_prices as
    (
    select
        distinct
        symbol as collateral_asset
        , date_trunc('day', to_timestamp(timestamp)) as report_date
        , first_value(current_price) over (partition by
        symbol, date_trunc('day', to_timestamp(timestamp)) order by timestamp)
        as osm_price_open
        , last_value(current_price) over (partition by
        symbol, date_trunc('day', to_timestamp(timestamp)) order by timestamp)
        as osm_price_close
    from
        maker_osm
    where to_timestamp(timestamp) >= current_date - 30
        and current_price > 0
    order by 2 asc),
    daily_asset_return as (
    select
        collateral_asset
        , report_date
        , osm_price_open
        , osm_price_close
        , ((osm_price_close / osm_price_open) - 1) as intraday_return
    from
        osm_prices
    order by 1,2)
    select
    collateral_asset
    , stddev(intraday_return) * sqrt(365) as annualized_volatility
    from
    daily_asset_return
    group by 1
    order by 2 desc
    """
    )

    # volatility actions
    df_volatility_actions = df_cr_increase_actions.loc[
        df_cr_increase_actions["report_date"]
        >= pd.to_datetime(datetime.now() - timedelta(30))
    ]
    df_volatility_actions = (
        df_volatility_actions.groupby(["vault", "ilk", "collateral_asset"])
        .sum()
        .reset_index()
    )
    df_volatility_actions.rename(
        columns={"cr_increase_actions": "cr_increase_actions_total"}, inplace=True
    )

    df_volatility_actions = pd.merge(
        df_volatility_actions,
        df_annualized_volatility,
        how="left",
        on="collateral_asset",
    )
    df_volatility_actions["volatility_actions_30d"] = (
        df_volatility_actions["cr_increase_actions_total"]
        / df_volatility_actions["annualized_volatility"]
    )

    low_risk_percentile = np.percentile(
        df_volatility_actions["volatility_actions_30d"], 85, axis=0
    )
    medium_risk_percentile = np.percentile(
        df_volatility_actions["volatility_actions_30d"], 70, axis=0
    )

    df_volatility_actions["volatility_actions_30d_low"] = np.where(
        df_volatility_actions["volatility_actions_30d"] > low_risk_percentile, 1, 0
    )
    df_volatility_actions["volatility_actions_30d_medium"] = np.where(
        df_volatility_actions["volatility_actions_30d"] > medium_risk_percentile, 1, 0
    )

    # filtering CR increase actions only during major collateral price drops
    # (top N recent)
    df_cr_increase_actions_price_drop = pd.DataFrame()

    vault_types = list(df_cr_increase_actions["ilk"].unique())
    for vault_type in vault_types:

        # filter all vault type's vaults
        df_cr_increase_actions_vault_type = df_cr_increase_actions[
            df_cr_increase_actions["ilk"] == vault_type
        ]
        # get relevant price drop dates based on ilk's collateral asset
        if vault_type in VAULT_TYPE_TO_VAULT_ASSET_MAPPER:
            collateral_asset = VAULT_TYPE_TO_VAULT_ASSET_MAPPER[vault_type]
        elif vault_type in UNI_LP_VAULT_ASSET_MAP:
            # if collateral asset not in the vault type mapper (eg UNI LP vault type)
            # take WETH major price drops as a proxy  if in the collateral assets,
            # otherwise WBTC
            collateral_asset = (
                "WETH" if "WETH" in UNI_LP_VAULT_ASSET_MAP[vault_type] else "WBTC"
            )
        else:
            continue

        # filter out only top N most recently major price drops
        price_drops_asset = df_asset_price_drops[
            df_asset_price_drops["collateral_asset"] == collateral_asset
        ]["report_date"][:36]
        # filter only when during major price drops
        df_cr_increase_actions_vault_type = df_cr_increase_actions_vault_type[
            df_cr_increase_actions_vault_type["report_date"].isin(price_drops_asset)
        ]
        # append to the main df
        df_cr_increase_actions_price_drop = df_cr_increase_actions_price_drop.append(
            df_cr_increase_actions_vault_type
        )

    # number of unique price drop days protecting
    df_cr_increase_actions_price_drop_agg = (
        pd.DataFrame(
            df_cr_increase_actions_price_drop.groupby("vault").nunique()["report_date"]
        )
        .reset_index()
        .rename(columns={"report_date": "unique_price_drop_days_protected"})
    )
    # sum up all CR increase actions during all major price drop days
    df_cr_increase_total = (
        df_cr_increase_actions_price_drop.groupby("vault").sum().reset_index()
    )
    df_cr_increase_actions_price_drop_agg = pd.merge(
        df_cr_increase_total, df_cr_increase_actions_price_drop_agg, on="vault"
    )

    # number of CR increase actions
    action_thresholds = [5, 10, 15]
    for action_threshold in action_thresholds:
        column = "cr_increase_actions_{}".format(action_threshold)
        df_cr_increase_actions_price_drop_agg[column] = 0
        df_cr_increase_actions_price_drop_agg.loc[
            df_cr_increase_actions_price_drop_agg["cr_increase_actions"]
            >= action_threshold,
            column,
        ] = 1

    # number of unique price drop days protected
    action_thresholds = [2, 3, 5]
    for action_threshold in action_thresholds:
        column = "unique_price_drop_days_protected_{}".format(action_threshold)
        df_cr_increase_actions_price_drop_agg[column] = 0
        df_cr_increase_actions_price_drop_agg.loc[
            df_cr_increase_actions_price_drop_agg["unique_price_drop_days_protected"]
            >= action_threshold,
            column,
        ] = 1

    df_protection_scores = pd.merge(
        df_cr_increase_actions_price_drop_agg,
        df_volatility_actions[
            [
                "vault",
                "volatility_actions_30d_low",
                "volatility_actions_30d_medium",
            ]
        ],
        how="left",
        on="vault",
    )

    # recent activity indicators

    df_recent_activity = run_query(
        """
    with
    vault_recent_activity as (

        select
            vault_uid as vault
            , sum(case when to_timestamp(a.timestamp) >= current_date - 7 then 1 else 0 end)
            as unique_actions_7d
            , sum(case when to_timestamp(a.timestamp) >= current_date - 30 then 1 else 0 end)
            as unique_actions_30d
            , sum(case when to_timestamp(a.timestamp) >= current_date - 90 then 1 else 0 end)
            as unique_actions_90d
        from
            maker_vaulteventstate a
        join
            maker_ilk b
        on
            a.ilk = b.ilk
        where
            to_timestamp(a.timestamp) >= current_date - 90
        and
            type in ('asset', 'lp')
        group by 1
        order by 2 desc)
    select
        *
        , case when unique_actions_7d >= 10 then 1 else 0 end as unique_actions_7d_10
        , case when unique_actions_30d >= 10 then 1 else 0 end as unique_actions_30d_10
        , case when unique_actions_90d >= 10 then 1 else 0 end as unique_actions_90d_10
    from
        vault_recent_activity
    """
    )

    df_protection_scores = pd.merge(
        df_protection_scores, df_recent_activity, on="vault", how="left"
    ).fillna(0)
    del df_recent_activity

    df_active_vaults = run_query(
        """

        select
            uid as vault
            , ilk as vault_type
            , (collateralization / 100)::numeric(20,2) as cur_cr
            , ratio as cur_lr
            , is_institution
            , debt as total_debt_dai
            , case when protection_service is not null then 1 else 0 end
            as protection_service
            , case when collateralization/100 >  ratio*1.5 then 1 else 0 end
            as cur_cr_risk_1_5x
            , case when collateralization/100 >  ratio*2 then 1 else 0 end
            as cur_cr_risk_2x
            , case when collateralization/100 > ratio*3 then 1 else 0 end
            as cur_cr_risk_3x
        from
            maker_vault a
        join
            maker_ilk b
        using
            (ilk)
        where
            type in ('asset', 'lp')
        and
            a.is_active is true

    """
    )

    df_protection_scores = pd.merge(
        df_active_vaults, df_protection_scores, on="vault", how="left"
    ).fillna(0)
    del df_active_vaults

    df_vault_protections = run_query(
        """

    with
        vault_operations as (
    -- all CR increase actions in the recent period
    select
        vault_uid as vault
        , a.ilk
        , lr
        , b.collateral as collateral_asset
        , date_trunc('day', to_timestamp(a.timestamp)) as report_date
        , min(to_timestamp(a.timestamp)) as event_dts
    from
        maker_vaulteventstate a
    join
        maker_ilk b
    on
        a.ilk = b.ilk
    where
        after_ratio > before_ratio
    and
        to_timestamp(a.timestamp) > current_date - 180
    and
        type in ('asset', 'lp')
    and
        operation in ('DEPOSIT', 'PAYBACK', 'PAYBACK-WITHDRAW')
    group by 1,2,3,4,5),

    vault_operations_min_price as (
    -- replicate vault state with the minimum price within the next 24 h
    select
        vault
        , a.ilk
        , lr
        , report_date
        , event_dts
        , b.operation
        , a.collateral_asset
        , before_collateral::numeric(20,2)
        , before_principal::numeric(20,2)
        , min(current_price)::numeric(20,2) as min_osm_price
    from
        vault_operations a
    join
        maker_vaulteventstate b
    on
        a.event_dts = to_timestamp(b.timestamp)
    and
        a.vault = b.vault_uid
    join
        maker_osm c
    on
        to_timestamp(c.timestamp) between a.event_dts and a.event_dts + interval '24 hours'
    and
        a.collateral_asset = c.symbol
    group by 1,2,3,4,5,6,7,8,9),

    vault_events_liquidatable as (

    select
        *
        , (before_collateral*min_osm_price / nullif(before_principal,0))::numeric(20,2)
            as min_cr
    from
        vault_operations_min_price),
    vault_protections as (
    select
        a.*
        , case when min_cr < lr then 1 else 0 end as liquidatable
        , max(case when b.operation = 'LIQUIDATE' then 1 else 0 end) as liquidated
    from
        vault_events_liquidatable a
    left join
        maker_vaulteventstate b
    on
        a.vault = b.vault_uid
    and
        to_timestamp(b.timestamp) between event_dts and event_dts + interval '24 hours'
    and
        a.before_collateral > 0 and a.before_principal > 0
    group by 1,2,3,4,5,6,7,8,9,10,11,12),

    vault_protections_agg as (

    select
        vault
        , sum(case when liquidatable = 1 and liquidated = 0 then 1 else 0 end)
        as liquidation_protections
    from
        vault_protections
    group by 1
    order by 2 desc)

    select
        *
        , case when liquidation_protections > 1 then 1 else 0 end
        as liquidation_protections_1
        , case when liquidation_protections > 3 then 1 else 0 end
        as liquidation_protections_3
        , case when liquidation_protections > 5 then 1 else 0 end
        as liquidation_protections_5
    from
        vault_protections_agg

    """
    )

    df_protection_scores = pd.merge(
        df_protection_scores, df_vault_protections, on="vault", how="left"
    ).fillna(0)
    del df_vault_protections

    df_protection_scores["low_risk"] = (
        df_protection_scores["protection_service"]
        + df_protection_scores["cur_cr_risk_3x"]
        + df_protection_scores["unique_price_drop_days_protected_3"]
        + df_protection_scores["volatility_actions_30d_low"]
        + df_protection_scores["liquidation_protections_5"]
        > 0
    )
    df_protection_scores["medium_risk"] = (
        df_protection_scores["cur_cr_risk_1_5x"]
        + df_protection_scores["unique_price_drop_days_protected_2"]
        + df_protection_scores["unique_actions_30d_10"]
        + df_protection_scores["volatility_actions_30d_medium"]
        + df_protection_scores["liquidation_protections_1"]
        > 0
    )

    return df_protection_scores


def save_protection_score():
    vaults_to_update = []
    protection_scores_to_create = []
    df_protection_scores = get_protection_score_data()
    dt = datetime.now()
    timestamp = dt.timestamp()
    for row in df_protection_scores.itertuples(index=False):
        if row.low_risk:
            protection_score = "low"
        elif row.medium_risk:
            protection_score = "medium"
        else:
            protection_score = "high"

        if row.is_institution:
            protection_score = "low"

        vaults_to_update.append(Vault(uid=row.vault, protection_score=protection_score))

        protection_scores_to_create.append(
            VaultProtectionScore(
                timestamp=timestamp,
                datetime=dt,
                vault_uid=row.vault,
                ilk=row.vault_type,
                cur_cr=row.cur_cr,
                total_debt_dai=row.total_debt_dai,
                protection_service=row.protection_service,
                cur_lr=row.cur_lr,
                cr_increase_actions=row.cr_increase_actions,
                unique_price_drop_days_protected=row.unique_price_drop_days_protected,
                cr_increase_actions_5=row.cr_increase_actions_5,
                cr_increase_actions_10=row.cr_increase_actions_10,
                cr_increase_actions_15=row.cr_increase_actions_15,
                unique_price_drop_days_protected_2=(
                    row.unique_price_drop_days_protected_2
                ),
                unique_price_drop_days_protected_3=(
                    row.unique_price_drop_days_protected_3
                ),
                unique_price_drop_days_protected_5=(
                    row.unique_price_drop_days_protected_5
                ),
                unique_actions_7d=row.unique_actions_7d,
                unique_actions_30d=row.unique_actions_30d,
                unique_actions_90d=row.unique_actions_90d,
                unique_actions_7d_10=row.unique_actions_7d_10,
                unique_actions_30d_10=row.unique_actions_30d_10,
                unique_actions_90d_10=row.unique_actions_90d_10,
                cur_cr_risk_1_5x=row.cur_cr_risk_1_5x,
                cur_cr_risk_2x=row.cur_cr_risk_2x,
                cur_cr_risk_3x=row.cur_cr_risk_3x,
                volatility_actions_30d_low=row.volatility_actions_30d_low,
                volatility_actions_30d_medium=row.volatility_actions_30d_medium,
                liquidation_protections=row.liquidation_protections,
                liquidation_protections_1=row.liquidation_protections_1,
                liquidation_protections_3=row.liquidation_protections_3,
                liquidation_protections_5=row.liquidation_protections_5,
                protection_score=protection_score,
            )
        )
    del df_protection_scores

    bulk_update_models(
        vaults_to_update,
        update_field_names=["protection_score"],
        pk_field_names=["uid"],
    )
    VaultProtectionScore.objects.bulk_create(
        protection_scores_to_create, batch_size=500
    )
