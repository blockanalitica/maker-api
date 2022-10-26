# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging
import time
from datetime import datetime
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.query_utils import Q
from django_bulk_load import bulk_insert_models, bulk_update_models

from maker.modules.osm import get_medianizer_address
from maker.sources.defisaver import get_defisaver_chain_data, get_defisaver_vault_data
from maker.utils.metrics import auto_named_statsd_timer

from ..models import (
    OSM,
    Ilk,
    MakerAsset,
    MarketPrice,
    Vault,
    VaultOwner,
    VaultsLiquidation,
)
from ..modules.events import save_last_activity
from ..sources import makerburn
from ..sources.blockanalitica import fetch_ilk_vaults
from ..sources.dicu import get_vaults_data
from ..sources.maker_changelog import get_addresses_for_asset

log = logging.getLogger(__name__)


@auto_named_statsd_timer
def save_ilks():
    collaterals = makerburn.get_collateral_list()
    timestamp = int(time.time())
    for collateral in collaterals:
        ilk = collateral["ilk"]

        if collateral["psm_adr"]:
            collateral_type = "psm"
        elif collateral["is_uni_v2"] or "CRVV1" in ilk or "GUNI" in ilk:
            collateral_type = "lp"
        elif collateral["is_rwa"] or ilk.startswith("RWA"):
            collateral_type = "rwa"
        elif collateral["is_sc"]:
            collateral_type = "stable"
        elif "DIRECT" in ilk:
            collateral_type = "d3m"
        elif "TELEPORT" in ilk:
            collateral_type = "teleport"
        else:
            collateral_type = "asset"

        name = collateral["name"]
        if collateral_type == "psm":
            symbol = ilk.split("-")[1]
            if symbol == "PAX":
                symbol = "USDP"
        elif collateral["ilk"] == "DIRECT-AAVEV2-DAI":
            symbol = "AAVE"
        else:
            symbol = ilk.split("-")[0]

        if "DAIUSDC" in ilk or "USDCDAI" in ilk:
            is_stable = True
        else:
            is_stable = bool(collateral["is_sc"])

        if collateral_type == "lp" and is_stable:
            collateral_type = "lp-stable"

        ilk_data = {
            "name": name,
            "collateral": symbol,
            "dai_debt": collateral["dai"],
            "debt_ceiling": collateral["cap_temp"],
            "dc_iam_line": collateral["dc_iam_line"],
            "dc_iam_gap": collateral["dc_iam_gap"],
            "dc_iam_ttl": collateral["dc_iam_ttl"],
            "lr": collateral["liq_ratio"],
            "locked": collateral["locked"],
            "osm_price": collateral["price"],
            "osm_price_next": collateral["next_price"],
            "chop": collateral["liq_2_0_chop"],
            "hole": collateral["liq_2_0_hole"],
            "buf": collateral["liq_2_0_buf"],
            "tail": collateral["liq_2_0_tail"],
            "cusp": collateral["liq_2_0_cusp"],
            "chip": collateral["liq_2_0_chip"],
            "tip": collateral["liq_2_0_tip"],
            "step": collateral["liq_2_0_step"],
            "cut": collateral["liq_2_0_cut"],
            "stability_fee": round(collateral["fee"] ** (60 * 60 * 24 * 365) - 1, 4),
            "fee_in": collateral["psm_fee_in"],
            "fee_out": collateral["psm_fee_out"],
            "dust": collateral["dust"],
            "timestamp": timestamp,
            "type": collateral_type,
            "is_active": collateral["cap_temp"] > 0 or collateral["dai"] > 0,
            "has_liquidations": bool(collateral["is_liq_2_0"]),
            "is_stable": is_stable,
        }

        ilk_obj, created = Ilk.objects.get_or_create(ilk=ilk, defaults=ilk_data)
        if created:
            ilk_obj.name = name
            ilk_obj.collateral = symbol
            ilk_obj.save()
            if ilk_obj.type in ["asset", "lp"]:
                address, oracle_address = get_addresses_for_asset(ilk_obj.collateral)
                medianizer_address = get_medianizer_address(oracle_address)
                MakerAsset.objects.update_or_create(
                    symbol=ilk.collateral,
                    defaults=dict(
                        address=address.lower(),
                        oracle_address=oracle_address.lower(),
                        medianizer_address=medianizer_address.lower(),
                        is_active=True,
                        type=ilk_obj.type,
                    ),
                )
        else:
            Ilk.objects.filter(ilk=ilk).update(**ilk_data)


def _upsert_and_fetch_owner_data(ilk):
    vault_owners = {}
    vault_map = {}
    owner_map = {}
    for vault in fetch_ilk_vaults(ilk):
        vault_map[str(vault["vault_uid"])] = {
            "ds_proxy": vault["ds_proxy"],
            "owner_address": vault["owner_address"],
        }
        if vault["owner_address"]:
            vault_owners[vault["owner_address"]] = {"ens": vault["owner_ens"]}

    for address, owner_data in vault_owners.items():
        owner, _ = VaultOwner.objects.get_or_create(address=address)
        if owner.ens != owner_data["ens"]:
            owner.ens = owner_data["ens"]
            owner.save(update_fields=["ens"])

        owner_map[address] = {
            "owner_name": owner.name,
            "ens": owner.ens,
            "is_institution": "institution" in (owner.tags or []),
        }
    return vault_map, owner_map


@auto_named_statsd_timer
def create_or_update_vaults(ilk):
    ilk_obj = Ilk.objects.get(ilk=ilk)
    market_price = None
    if ilk_obj.type == "asset":
        collateral_symbol = ilk_obj.collateral
        try:
            market_price = (
                MarketPrice.objects.filter(symbol=collateral_symbol).latest().price
            )
        except MarketPrice.DoesNotExist:
            pass
    bulk_create = []
    bulk_update = []
    run_timestamp = datetime.now().timestamp()
    dt = datetime.now()
    updated_fields = [
        "urn",
        "ilk",
        "collateral",
        "art",
        "debt",
        "principal",
        "accrued_fees",
        "paid_fees",
        "collateralization",
        "osm_price",
        "mkt_price",
        "ratio",
        "liquidation_price",
        "available_collateral",
        "available_debt",
        "ds_proxy_address",
        "block_created",
        "block_number",
        "block_timestamp",
        "block_datetime",
        "timestamp",
        "datetime",
        "is_active",
        "modified",
        "collateral_symbol",
        "is_at_risk",
        "is_at_risk_market",
        "liquidation_drop",
        "protection_score",
        "owner_address",
        "owner_ens",
        "owner_name",
        "is_institution",
    ]

    osm_price = None
    if ilk_obj.type in ["asset", "lp"]:
        osm = OSM.objects.filter(symbol=ilk_obj.collateral).latest()
        osm_price = min(osm.current_price, osm.next_price)

    vault_map, owner_map = _upsert_and_fetch_owner_data(ilk)

    for data in get_vaults_data(ilk):
        try:
            vault = Vault.objects.get(uid=data["uid"], ilk=ilk)
            created = False
        except Vault.DoesNotExist:
            vault = Vault(uid=data["uid"], ilk=ilk)
            created = True

        datalake_vault = vault_map.get(data["uid"])
        if datalake_vault:
            vault.ds_proxy_address = datalake_vault["ds_proxy"]
            vault.owner_address = datalake_vault["owner_address"]

            owner_data = owner_map.get(datalake_vault["owner_address"])
            if owner_data:
                vault.owner_ens = owner_data["ens"]
                vault.owner_name = owner_data["owner_name"]
                vault.is_institution = owner_data["is_institution"]
            else:
                vault.owner_ens = None
                vault.owner_name = None
                vault.is_institution = None
        else:
            log.debug("Couldn't find vault %s in datalake", data["uid"])
            vault.ds_proxy_address = None
            vault.owner_address = None
            vault.owner_ens = None
            vault.owner_name = None
            vault.is_institution = None

        vault.urn = data["urn"]
        vault.collateral_symbol = ilk_obj.collateral
        vault.collateral = max(0, Decimal(str(data["collateral"])))
        vault.art = Decimal(str(data["art"]))
        vault.debt = Decimal(str(data["debt"]))
        vault.principal = Decimal(str(data["principal"]))
        vault.accrued_fees = Decimal(str(data["accrued_fees"]))
        vault.paid_fees = Decimal(str(data["paid_fees"]))
        vault.collateralization = (
            Decimal(str(data["collateralization"]))
            if data["collateralization"]
            else None
        )
        vault.osm_price = Decimal(str(data["osm_price"])) if data["osm_price"] else None
        vault.mkt_price = market_price
        vault.ratio = Decimal(str(data["ratio"])) if data["ratio"] else None
        vault.liquidation_price = (
            Decimal(str(data["liquidation_price"])) if data["liquidation_price"] else 0
        )
        vault.available_collateral = Decimal(str(data["available_collateral"]))
        vault.available_debt = Decimal(str(data["available_debt"]))
        vault.block_created = data["block_created"]
        vault.block_number = data["last_block"]
        vault.block_timestamp = data["last_time"].timestamp()
        vault.block_datetime = data["last_time"]
        vault.timestamp = run_timestamp
        vault.datetime = dt
        vault.is_active = data["collateral"] > 0 and data["debt"] >= 0.1
        vault.modified = datetime.utcnow()
        if vault.protection_service:
            vault.protection_score = "low"

        vault.is_at_risk = False
        vault.is_at_risk_market = False
        if vault.is_active:
            if osm_price:
                vault.is_at_risk = vault.liquidation_price >= osm_price
                if not ilk_obj.is_stable:
                    vault.liquidation_drop = round(
                        1 - (vault.liquidation_price / osm_price), 2
                    )
            else:
                if ilk_obj.type in ["asset", "lp"]:
                    vault.is_at_risk = vault.liquidation_price >= vault.osm_price
            if market_price:
                vault.is_at_risk_market = vault.liquidation_price >= market_price
        else:
            vault.liquidation_drop = 0

        if created:
            bulk_create.append(vault)
            if len(bulk_create) == 1000:
                bulk_insert_models(bulk_create)
                bulk_create = []
        else:
            bulk_update.append(vault)
            if len(bulk_update) == 1000:
                bulk_update_models(
                    bulk_update,
                    update_field_names=updated_fields,
                    pk_field_names=["uid", "ilk"],
                )
                bulk_update = []

    if len(bulk_create) > 0:
        bulk_insert_models(bulk_create, ignore_conflicts=True)

    if len(bulk_update) > 0:
        bulk_update_models(
            bulk_update,
            update_field_names=updated_fields,
            pk_field_names=["uid", "ilk"],
        )
    get_defisaver_chain_data(ilk)
    if ilk_obj.type in ["asset", "lp"]:
        generate_vaults_liquidation(ilk)
    update_ilk_with_vaults_stats(ilk)
    save_last_activity(ilk)


def update_ilk_with_vaults_stats(ilk):
    info = Vault.objects.filter(ilk=ilk, is_active=True).aggregate(
        total_debt=Sum("debt"), vaults_count=Count("id")
    )
    Ilk.objects.filter(ilk=ilk).update(
        total_debt=info["total_debt"] or Decimal("0"),
        vaults_count=info["vaults_count"] or 0,
    )


def sync_vaults_with_defisaver():

    vaults = Vault.objects.filter(is_at_risk=True, is_active=True)

    for vault in vaults:
        payload, liquidated = get_defisaver_vault_data(vault.uid)
        # if it's liquidated, or collateralization is MASSIVE set it to inactive.
        # Defisaver returns massive collateralization in some weird cases, so to avoid
        # getting errors when updating the Vault, just update the is_active and call
        # it a day.

        if liquidated or (payload and payload["collateralization"] > 10**14):
            vault.is_active = False
            vault.is_at_risk = False
            vault.save(update_fields=["is_active", "is_at_risk"])
        else:
            if not payload:
                continue
            vault.collateral = payload["collateral"]
            vault.debt = payload["debt"]
            vault.collateralization = payload["collateralization"]
            vault.liquidation_price = payload["liquidation_price"]
            vault.is_active = payload["collateral"] > 0 and payload["debt"] >= 1
            price = min(payload["price"], payload["next_price"])
            vault.is_at_risk = vault.liquidation_price >= price
            vault.save(
                update_fields=[
                    "collateral",
                    "debt",
                    "collateralization",
                    "liquidation_price",
                    "is_active",
                    "is_at_risk",
                ]
            )


def get_cr(lr, drop):
    return lr / (1 - drop)


def generate_vaults_liquidation(ilk):
    vault_ilk = Ilk.objects.get(ilk=ilk)
    osm_price = OSM.objects.latest_for_asset(vault_ilk.collateral)
    for x in range(1, 81):
        drop = round(Decimal(x / 100), 2)
        cr = get_cr(vault_ilk.lr, drop)
        expected_price = Decimal(
            osm_price.current_price - Decimal((osm_price.current_price * Decimal(drop)))
        )
        for type in ["all", "high", "medium", "low"]:
            if type == "all":
                vaults = Vault.objects.filter(ilk=ilk, is_active=True,).aggregate(
                    total_debt=Sum(
                        "debt",
                        filter=Q(
                            liquidation_price__gte=expected_price,
                        ),
                    ),
                    debt=Sum(
                        "debt",
                        filter=Q(
                            liquidation_drop=drop,
                        ),
                    ),
                )
            else:
                vaults = Vault.objects.filter(
                    ilk=ilk,
                    is_active=True,
                    protection_score=type,
                ).aggregate(
                    total_debt=Sum(
                        "debt",
                        filter=Q(
                            liquidation_price__gte=expected_price,
                        ),
                    ),
                    debt=Sum(
                        "debt",
                        filter=Q(
                            liquidation_drop=drop,
                        ),
                    ),
                )
            VaultsLiquidation.objects.update_or_create(
                ilk=ilk,
                drop=x,
                type=type,
                defaults={
                    "cr": cr,
                    "total_debt": vaults["total_debt"] or 0,
                    "expected_price": expected_price,
                    "current_price": osm_price.current_price,
                    "debt": vaults["debt"] or 0,
                },
            )
