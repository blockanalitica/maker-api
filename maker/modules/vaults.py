# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta
from maker.sources.cortex import fetch_cortex_urn_states
from web3 import Web3
from django_bulk_load import bulk_insert_models
from maker.utils.blockchain.chain import Blockchain

from ..models import Ilk, RawEvent, Vault, VaultEventState, UrnEventState
from maker.utils.metrics import auto_named_statsd_timer

MAKER_MCD_VAT = "0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B"


def get_ilk_data(ilk):
    chain = Blockchain()
    contract = chain.get_contract(MAKER_MCD_VAT)
    return contract.caller.ilks(ilk)


def get_ilk_debt(ilk):
    ilk_bytes = Web3.toHex(text=ilk)
    data = get_ilk_data(ilk_bytes)
    rate = data[1] / 1e27
    art = data[0]
    return (art * rate) / 1e18


def save_vaults_changes():
    for ilk in Ilk.objects.all():
        get_vault_changes(ilk.ilk)


def get_vault_changes(ilk):
    Vault.objects.filter(ilk=ilk).update(
        collateral_change_1d=0,
        collateral_change_7d=0,
        collateral_change_30d=0,
        principal_change_1d=0,
        principal_change_7d=0,
        principal_change_30d=0,
    )

    for days_ago in [1, 7, 30]:
        time_diff = (datetime.now() - timedelta(days=days_ago)).timestamp()
        for vault_data in (
            VaultEventState.objects.filter(
                ilk=ilk,
                timestamp__gte=time_diff,
            )
            .order_by("vault_uid")
            .distinct("vault_uid")
            .values("vault_uid", "ilk")
        ):
            save_vault_changes(vault_data, days_ago)


def save_vault_changes(vault_data, days_ago):
    time_diff = (datetime.now() - timedelta(days=days_ago)).timestamp()
    try:
        vault = Vault.objects.get(uid=vault_data["vault_uid"], ilk=vault_data["ilk"])
    except Vault.DoesNotExist:
        return

    latest_position = VaultEventState.objects.filter(
        vault_uid=vault_data["vault_uid"], ilk=vault_data["ilk"]
    ).latest()
    try:
        start_position = VaultEventState.objects.filter(
            vault_uid=vault_data["vault_uid"],
            ilk=vault_data["ilk"],
            timestamp__lte=time_diff,
        ).latest()
        setattr(
            vault,
            f"collateral_change_{days_ago}d",
            round(
                (latest_position.after_collateral or 0)
                - (start_position.before_collateral or 0),
                4,
            ),
        )
        setattr(
            vault,
            f"principal_change_{days_ago}d",
            round(
                (latest_position.after_principal or 0)
                - (start_position.before_principal or 0),
                4,
            ),
        )
    except VaultEventState.DoesNotExist:
        setattr(
            vault,
            f"collateral_change_{days_ago}d",
            latest_position.after_collateral or 0,
        )
        setattr(
            vault,
            f"principal_change_{days_ago}d",
            latest_position.after_principal or 0,
        )
    vault.save()


# ATLAS-API DATA


@auto_named_statsd_timer
def save_urn_event_states():
    latest_block = UrnEventState.latest_block_number()
    urn_states_data = fetch_cortex_urn_states(latest_block)
    bulk_create = []
    for urn_state in urn_states_data:
        bulk_create.append(UrnEventState(**urn_state))
        if len(bulk_create) >= 1000:
            bulk_insert_models(bulk_create, ignore_conflicts=True)
            bulk_create = []

    if bulk_create:
        bulk_insert_models(bulk_create, ignore_conflicts=True)
