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
from eth_utils import to_bytes

from maker.constants import MCD_VAT_CONTRACT_ADDRESS
from maker.modules.osm import get_medianizer_address
from maker.sources.cortex import fetch_cortext_ilk_vaults
from maker.utils.blockchain.chain import Blockchain
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
from ..sources import makerburn
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
        elif ilk == "RWA014-A":
            collateral_type = "psm"
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
            elif collateral["ilk"] == "RWA014-A":
                symbol = "USDC"
        elif collateral["ilk"] == "DIRECT-AAVEV2-DAI":
            symbol = "AAVE"
        elif collateral["ilk"] == "DIRECT-COMPV2-DAI":
            symbol = "COMP"

        else:
            symbol = ilk.split("-")[0]

        if "DAIUSDC" in ilk or "USDCDAI" in ilk:
            is_stable = True
        else:
            is_stable = bool(collateral["is_sc"])

        if collateral_type == "lp" and is_stable:
            collateral_type = "lp-stable"

        dc_iam_line = collateral["dc_iam_line"]
        debt = collateral["dai"]
        if collateral["ilk"] == "RWA014-A":
            chain = Blockchain()
            contract = chain.get_contract(MCD_VAT_CONTRACT_ADDRESS)
            data = contract.functions.ilks(to_bytes(text=ilk)).call(
                block_identifier="latest"
            )
            debt = Decimal(data[0]) / 10**18
            dc_iam_line = Decimal(data[3]) / 10**45
        if collateral["ilk"] == "PSM-PAX-A":
            dc_iam_line = 0

        ilk_data = {
            "name": name,
            "collateral": symbol,
            "dai_debt": debt,
            "debt_ceiling": collateral["cap_temp"],
            "dc_iam_line": dc_iam_line,
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


@auto_named_statsd_timer
def create_or_update_vaults(ilk, force=False):
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

    dt = datetime.now()
    updated_fields = [
        "uid",
        "urn",
        "ilk",
        "collateral",
        "art",
        "debt",
        "collateralization",
        "osm_price",
        "ratio",
        "liquidation_price",
        "ds_proxy_address",
        "block_number",
        "block_datetime",
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
        "ds_proxy_name",
        "last_activity",
        "collateral_change_1d",
        "collateral_change_7d",
        "collateral_change_30d",
        "principal_change_1d",
        "principal_change_7d",
        "principal_change_30d",
    ]

    for data in fetch_cortext_ilk_vaults(ilk, force=force):
        try:
            vault = Vault.objects.get(urn=data["urn"], ilk=ilk)
            created = False
        except Vault.DoesNotExist:
            vault = Vault(urn=data["urn"], ilk=ilk)
            created = True
        owner = None
        if data["owner"]:
            owner, _ = VaultOwner.objects.get_or_create(address=data["owner"])

        vault.ds_proxy_address = data["proxy"]
        vault.owner_address = data["owner"]
        vault.owner_ens = owner.ens if owner else None
        vault.owner_name = owner.name if owner else None
        vault.is_institution = "institution" in (owner.tags or []) if owner else False
        uid = data["vault"]
        if uid is None:
            uid = data["urn"][:10]

        if (
            data["urn"] == "0xd359b2f80bf9efd66c43ed302a839c9f37965535"
            and ilk == "ETH-A"
        ):
            uid = data["urn"][:10]
        vault.uid = uid
        vault.collateral_symbol = ilk_obj.collateral
        vault.collateral = max(0, Decimal(str(data["collateral"])))
        vault.art = Decimal(str(data["art"]))
        vault.debt = Decimal(str(data["debt"]))
        vault.last_activity = data["datetime"]
        vault.osm_price = Decimal(str(data["osm_price"])) if data["osm_price"] else None
        if vault.osm_price:
            vault.collateralization = (
                ((vault.collateral * vault.osm_price) / vault.debt) * 100
                if vault.debt
                else None
            )
        vault.ratio = Decimal(str(data["ratio"])) if data["ratio"] else None
        vault.liquidation_price = (
            Decimal(str(data["liquidation_price"])) if data["liquidation_price"] else 0
        )

        vault.block_number = data["block_number"]
        vault.block_datetime = data["datetime"]
        vault.datetime = dt
        vault.is_active = (
            Decimal(data["collateral"]) > 0 and Decimal(data["debt"]) >= 0.1
        )
        vault.collateral_change_1d = data["ink_change_1d"]
        vault.collateral_change_7d = data["ink_change_7d"]
        vault.collateral_change_30d = data["ink_change_30d"]
        vault.principal_change_1d = data["art_change_1d"]
        vault.principal_change_7d = data["art_change_7d"]
        vault.principal_change_30d = data["art_change_30d"]
        vault.modified = datetime.utcnow()
        if vault.protection_service:
            vault.protection_score = "low"

        vault.is_at_risk = False
        vault.is_at_risk_market = False
        if vault.is_active:
            if vault.osm_price:
                vault.is_at_risk = vault.liquidation_price >= vault.osm_price
                if not ilk_obj.is_stable:
                    vault.liquidation_drop = round(
                        1 - (vault.liquidation_price / vault.osm_price), 2
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
                    pk_field_names=["urn", "ilk"],
                )
                bulk_update = []

    if len(bulk_create) > 0:
        bulk_insert_models(bulk_create, ignore_conflicts=True)

    if len(bulk_update) > 0:
        bulk_update_models(
            bulk_update,
            update_field_names=updated_fields,
            pk_field_names=["urn", "ilk"],
        )

    if force is True:
        return
    if ilk_obj.type in ["asset", "lp"]:
        generate_vaults_liquidation(ilk)
    update_ilk_with_vaults_stats(ilk)


def update_ilk_with_vaults_stats(ilk):
    info = Vault.objects.filter(ilk=ilk, is_active=True).aggregate(
        total_debt=Sum("debt"), vaults_count=Count("id")
    )
    Ilk.objects.filter(ilk=ilk).update(
        total_debt=info["total_debt"] or Decimal("0"),
        vaults_count=info["vaults_count"] or 0,
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
                vaults = Vault.objects.filter(
                    ilk=ilk,
                    is_active=True,
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


def force_all_vaults():
    ilks = Ilk.objects.all().values_list("ilk", flat=True)
    for ilk in ilks:
        create_or_update_vaults(ilk=ilk, force=True)
