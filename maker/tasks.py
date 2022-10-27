# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from celery.schedules import crontab
from django.core.cache import cache
from django_bulk_load import bulk_update_models

from .celery import app
from .constants import DRAWDOWN_PAIRS_HISTORY_DAYS, OHLCV_TYPE_DAILY, OHLCV_TYPE_HOURLY
from .models import (
    OSM,
    Asset,
    GasPrice,
    Ilk,
    IlkHistoricStats,
    MakerAsset,
    Medianizer,
    OHLCVPair,
    Pool,
    SlippageDaily,
    SlippagePair,
    Vault,
    Volatility,
)
from .modules.asset import get_asset_total_supplies, save_assets_systemic_risk
from .modules.auctions import sync_auctions
from .modules.block import save_latest_blocks
from .modules.d3m import aave
from .modules.dai_growth import (
    sync_dai_supply_growth_periodical,
    sync_monthly_dai_supply,
)
from .modules.dai_trades import DAITradesFetcher
from .modules.defi import fetch_defi_balance, save_rates_for_protocols
from .modules.discord import (
    send_risk_premium_and_protection_score_alerts,
    send_vaults_at_risk_alert,
)
from .modules.events import save_events, sync_vault_event_states
from .modules.ilk import save_stats_for_vault
from .modules.ilks import create_or_update_vaults, save_ilks, sync_vaults_with_defisaver
from .modules.liquidations import (
    save_maker_liquidations,
    save_vaults_liquidation_snapshot,
)
from .modules.liquidity_score import calculate_liquidity_score_for_all_assets
from .modules.ohlcv import (
    calculate_volatility,
    save_yesterdays_histominute_ohlcv,
    sync_history_for_ohlcv_pair,
    sync_ohlcv_asset_pairs,
)
from .modules.osm import save_medianizer_prices, save_osm_daily, save_osm_for_asset
from .modules.pool import save_pool_info
from .modules.psm import claculate_and_save_psm_dai_supply
from .modules.risk import save_overall_stats, save_surplus_buffer
from .modules.risk_premium import compute_all_vault_types
from .modules.slippage import save_oneinch_slippages
from .modules.token_price_history import save_market_prices, sync_chainlink_rounds
from .modules.vault_protection_score import save_protection_score
from .modules.vaults import save_vaults_changes
from .modules.vaults_at_risk import (
    refresh_market_risk_for_vaults,
    refresh_vaults_at_risk,
)
from .sources.blocknative import fetch_gas_prices
from .sources.dicu import get_last_block_for_vaults
from .sources.maker_chain import sync_lr_for_ilk, sync_stability_fee_for_ilk
from .utils.utils import yesterday_date

log = logging.getLogger(__name__)


SCHEDULE = {
    "sync_vaults_with_defisaver_task": {
        "schedule": crontab(minute="*/1"),
    },
    "get_gas_task": {
        "schedule": crontab(minute="*/1"),
    },
    "sync_chainlink_rounds_task": {
        "schedule": crontab(minute="*/1"),
    },
    "save_latest_blocks_task": {
        "schedule": crontab(minute="*/1"),
    },
    "check_to_sync_vaults": {
        "schedule": crontab(minute="*/2"),
    },
    "update_vaults_market_price": {
        "schedule": crontab(minute="*/2"),
    },
    "sync_osm_task": {
        "schedule": crontab(minute="0-15/1"),
    },
    "sync_medianizer_prices_task": {
        "schedule": crontab(minute="*/10"),
    },
    "sync_ilks_task": {
        "schedule": crontab(minute="*/10"),
    },
    "save_maker_liquidations_task": {
        "schedule": crontab(minute="*/15"),
    },
    "save_asset_market_caps_task": {
        "schedule": crontab(minute="*/30"),
    },
    "get_slippage_for_slippage_pairs": {
        # Run every 30 minutes, but not at random times, so we can time other
        # tasks with new slippages that need it
        "schedule": crontab(minute="15,45"),
    },
    "send_vaults_at_risk_alert_task": {
        "schedule": crontab(minute="5-21/1"),
    },
    "save_vaults_liquidation_snapshot_task": {
        "schedule": crontab(minute="0", hour="*/1"),
    },
    "fetch_defi_balance_task": {
        "schedule": crontab(minute="0", hour="*/1"),
    },
    "sync_d3m_task": {
        "schedule": crontab(minute="0", hour="*/1"),
    },
    "save_rates_for_protocols_task": {
        "schedule": crontab(minute="0", hour="*/1"),
    },
    "save_ilk_stats_task": {
        "schedule": crontab(minute="0", hour="*/1"),
    },
    "save_vault_changes_task": {
        "schedule": crontab(minute="0", hour="*/1"),
    },
    "sync_dai_trades_from_stablecoin_science_task": {
        "schedule": crontab(minute="55", hour="*/1"),
    },
    "sync_ohlcv_asset_pairs_task": {
        "schedule": crontab(minute="1", hour="0"),
    },
    "save_yesterdays_histominute_ohlcv_for_drawdown_pairs": {
        "schedule": crontab(minute="5", hour="0"),
    },
    "sync_ohlcv_task": {
        "schedule": crontab(minute="15", hour="0"),
    },
    "save_osm_daily_task": {
        "schedule": crontab(minute="15", hour="0"),
    },
    "sync_pools_task": {
        "schedule": crontab(minute="30", hour="0"),
    },
    "save_backed_assets_task": {
        "schedule": crontab(minute="50", hour="0"),
    },
    "sync_ilk_params_task": {
        "schedule": crontab(minute="0", hour="1"),
    },
    "sync_volatility_task": {
        "schedule": crontab(minute="0", hour="2"),
    },
    "compute_risk_premiums_task": {
        "schedule": crontab(minute="0", hour="5"),
    },
    "calculate_liquidity_score_for_all_assets_task": {
        "schedule": crontab(minute="30", hour="23"),
    },
    "sync_dai_supply_growth_periodical_task": {
        "schedule": crontab(minute="55", hour="23"),
    },
    "sync_monthly_dai_supply_task": {
        # First day of the month
        "schedule": crontab(minute="0", hour="0", day_of_month="1"),
    },
    "set_active_slippages": {
        "schedule": crontab(minute="5", hour="0"),
    },
}

##############
#   TASKS    #
##############


@app.task
def sync_ilk_vaults_task(ilk):
    create_or_update_vaults(ilk)


@app.task
def save_vault_changes_task():
    save_vaults_changes()


@app.task
def sync_auctions_task():
    sync_auctions()


@app.task
def save_osm_for_asset_task(symbol):
    """
    We only want to fetch OSM prices when they change, so we limit when the check runs
    """
    dt_now = datetime.now()
    try:
        timestamp = OSM.objects.latest_for_asset(symbol).timestamp
    except OSM.DoesNotExist:
        timestamp = None
    else:
        osm_dt = datetime.fromtimestamp(timestamp)
        if osm_dt.hour == dt_now.hour:
            log.info(
                "Skipping sync_osm for %s as it has already been updated in the "
                "current hour %s",
                symbol,
                osm_dt.hour,
            )
            return
    save_osm_for_asset(symbol)
    refresh_vaults_at_risk(symbol)


@app.task
def save_medianizer_prices_task(symbol, medianizer_address, from_block):
    save_medianizer_prices(symbol, medianizer_address, from_block=from_block)


@app.task
def sync_ilk_params_task():
    sync_lr_for_ilk()
    sync_stability_fee_for_ilk()


@app.task
def save_oneinch_slippages_task(slippage_pair_id):
    save_oneinch_slippages(slippage_pair_id)


@app.task
def sync_history_for_ohlcv_pair_task(pair_id):
    pair = OHLCVPair.objects.get(id=pair_id)
    sync_history_for_ohlcv_pair(pair)


@app.task()
def save_yesterdays_histominute_ohlcv_task(
    from_asset_symbol, to_asset_symbol, exchange
):
    save_yesterdays_histominute_ohlcv(from_asset_symbol, to_asset_symbol, exchange)


@app.task
def sync_pool_task(pool_id):
    pool = Pool.objects.get(id=pool_id)
    save_pool_info(pool)


@app.task
def claculate_and_save_psm_dai_supply_task():
    claculate_and_save_psm_dai_supply()


#######################
#   PERIODIC TASKS    #
#######################


@app.task
def fetch_defi_balance_task():
    fetch_defi_balance()


@app.task
def save_vaults_liquidation_snapshot_task():
    save_vaults_liquidation_snapshot()


@app.task
def sync_vaults_with_defisaver_task():
    sync_vaults_with_defisaver()


@app.task
def save_backed_assets_task():
    save_assets_systemic_risk()


@app.task
def sync_ilks_task():
    save_ilks()


@app.task
def save_rates_for_protocols_task():
    save_rates_for_protocols()


@app.task
def sync_d3m_task():
    aave.save_d3m()
    save_surplus_buffer()
    save_overall_stats()


@app.task
def check_to_sync_vaults():
    block_number = get_last_block_for_vaults()
    if not block_number:
        log.error("Could not fetch latest block from Snowflake")
        return
    if Vault.objects.filter(block_number=block_number).count() > 0:
        log.info("Skiping sync_vaults for block_number %s", block_number)
        return
    sync_vaults_task.delay()
    sync_auctions_task.delay()


@app.task
def sync_vaults_task():
    save_events()
    sync_vault_event_states()
    for ilk in Ilk.objects.with_vaults().values_list("ilk", flat=True):
        sync_ilk_vaults_task.delay(ilk)
    claculate_and_save_psm_dai_supply_task.delay()


@app.task
def sync_osm_task():
    """Syncs OSM prices"""
    assets = MakerAsset.objects.filter(is_active=True)
    for asset in assets:
        save_osm_for_asset_task.apply_async(args=(asset.symbol,))


@app.task
def sync_medianizer_prices_task():
    assets = MakerAsset.objects.filter(
        is_active=True, medianizer_address__isnull=False, type="asset"
    )
    for asset in assets:
        try:
            latest_block_number = (
                Medianizer.objects.filter(symbol=asset.symbol).latest().block_number
            )
        except Medianizer.DoesNotExist:
            latest_block_number = 8936795

        save_medianizer_prices_task.apply_async(
            args=(
                asset.symbol,
                asset.medianizer_address,
                latest_block_number,
            )
        )


@app.task
def save_ilk_stats_task():
    for ilk in Ilk.objects.with_vaults().values_list("ilk", flat=True):
        save_stats_for_vault(ilk)

    dt = datetime.now()
    # Opposite query of `with_vaults` from ILKManager
    for ilk in Ilk.objects.exclude(type__in=["asset", "lp", "stable", "lp-stable"]):
        IlkHistoricStats.objects.create(
            ilk=ilk,
            datetime=dt,
            timestamp=dt.timestamp(),
            total_debt=ilk.dai_debt,
            dc_iam_line=ilk.dc_iam_line,
        )


@app.task
def compute_risk_premiums_task():
    save_protection_score()
    compute_all_vault_types()
    send_risk_premium_and_protection_score_alerts()


@app.task
def get_gas_task():
    data = fetch_gas_prices()
    asset = Asset.objects.get(symbol="WETH")
    data["eth_price"] = asset.price
    data["timestamp"] = int(datetime.now().timestamp())
    data["datetime"] = datetime.now()
    GasPrice.objects.create(**data)


@app.task
def calculate_liquidity_score_for_all_assets_task():
    calculate_liquidity_score_for_all_assets()


@app.task
def send_vaults_at_risk_alert_task():
    cache_key = "send_vaults_at_risk_alert_task:executed"
    if cache.get(cache_key):
        log.info(
            "send_vaults_at_risk_alert_task was already executed in the last 30 min"
        )
        return

    osm = OSM.objects.latest()
    if not osm:
        log.warning("Couldn't fetch latest OSM price")
        return

    # Only run this 5 minutes after the OSM update
    # This is so we let all the OSMs finish updating before we send alerts
    if datetime.now() - osm.datetime > timedelta(minutes=5):
        send_vaults_at_risk_alert()
        # Cache for 30 min
        cache.set(cache_key, datetime.now(), 60 * 30)


@app.task
def sync_dai_supply_growth_periodical_task():
    sync_dai_supply_growth_periodical()


@app.task
def sync_monthly_dai_supply_task():
    sync_monthly_dai_supply()


@app.task
def sync_dai_trades_from_stablecoin_science_task(days=30):
    # We're running this task on compute because it'll take ~120mb of RAM and we don't
    # want the container to crash.
    fetcher = DAITradesFetcher()
    fetcher.fetch(days=days)
    del fetcher


@app.task
def sync_ohlcv_asset_pairs_task():
    assets = MakerAsset.objects.filter(type="asset", is_active=True)
    for asset in assets:
        sync_ohlcv_asset_pairs(asset.symbol)


@app.task
def save_osm_daily_task():
    save_osm_daily()


@app.task
def get_slippage_for_slippage_pairs():
    slippage_pairs = []
    for slippage_pair in SlippagePair.objects.all():
        if not slippage_pair.last_run or (
            datetime.utcnow() - timedelta(hours=slippage_pair.interval)
            > slippage_pair.last_run
        ):
            slippage_pairs.append(slippage_pair)
    if slippage_pairs:
        for slippage_pair in slippage_pairs:
            save_oneinch_slippages_task.delay(slippage_pair.id)
            # save_zerox_slippages(slippage_pair)


@app.task
def set_active_slippages():
    SlippageDaily.objects.filter(is_active=True).update(is_active=False)
    SlippageDaily.objects.filter(date=yesterday_date()).update(is_active=True)


@app.task
def save_asset_market_caps_task():
    bulk_update = []
    data = get_asset_total_supplies()
    for asset in Asset.objects.all():
        total_supply = Decimal(data[asset.address] / 10**asset.decimals)
        asset.total_supply = total_supply
        asset.market_cap = total_supply * asset.price
        bulk_update.append(asset)

    if bulk_update:
        bulk_update_models(
            bulk_update,
            update_field_names=["total_supply", "market_cap"],
            pk_field_names=["id"],
        )


@app.task
def sync_chainlink_rounds_task():
    sync_chainlink_rounds()
    save_market_prices()


@app.task
def sync_ohlcv_task():
    pairs = OHLCVPair.objects.filter(is_active=True).values("id", "to_asset_symbol")
    # Make sure to first update pairs to USD symbol, as that's then used in the
    # underlying calculations for OHLCV. The code handles it correctly if it's not in
    # the correct order, but it can cause exceptions because of concurrent running
    # of different pairs.
    sorted_pairs = sorted(
        pairs,
        key=lambda p: "ZZZ" if p["to_asset_symbol"] == "USD" else p["to_asset_symbol"],
        reverse=True,
    )
    for pair in sorted_pairs:
        sync_history_for_ohlcv_pair_task.delay(pair["id"])


@app.task
def save_yesterdays_histominute_ohlcv_for_drawdown_pairs():
    for key in list(DRAWDOWN_PAIRS_HISTORY_DAYS.keys()):
        from_asset_symbol, to_asset_symbol, exchange, ohlcv_type = key.split("-")
        if ohlcv_type != OHLCV_TYPE_DAILY:
            continue

        pair = OHLCVPair.objects.get(
            from_asset_symbol=from_asset_symbol,
            to_asset_symbol=to_asset_symbol,
            exchange=exchange,
            ohlcv_type=OHLCV_TYPE_DAILY,
        )
        save_yesterdays_histominute_ohlcv_task.delay(
            pair.from_asset_symbol, pair.to_asset_symbol, pair.exchange
        )


@app.task
def sync_volatility_task():
    for key in list(DRAWDOWN_PAIRS_HISTORY_DAYS.keys()):
        from_asset_symbol, to_asset_symbol, exchange, ohlcv_type = key.split("-")
        if ohlcv_type != OHLCV_TYPE_HOURLY:
            continue

        pair = OHLCVPair.objects.get(
            from_asset_symbol=from_asset_symbol,
            to_asset_symbol=to_asset_symbol,
            exchange=exchange,
            ohlcv_type=OHLCV_TYPE_HOURLY,
        )
        for_date = date.today() - timedelta(days=1)

        volatility = calculate_volatility(pair, for_date=for_date)
        if volatility is None:
            continue

        Volatility.objects.create(pair=pair, date=for_date, volatility=volatility)


@app.task
def sync_pools_task():
    for pool in Pool.objects.filter(is_active=True):
        sync_pool_task.delay(pool.id)


@app.task
def save_latest_blocks_task():
    save_latest_blocks()


@app.task
def save_maker_liquidations_task():
    save_maker_liquidations()


@app.task
def update_vaults_market_price():
    for symbol in MakerAsset.objects.filter(type="asset", is_active=True).values_list(
        "symbol", flat=True
    ):
        refresh_market_risk_for_vaults(symbol)
