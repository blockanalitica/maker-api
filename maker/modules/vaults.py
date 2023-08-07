# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta

from web3 import Web3

from maker.utils.blockchain.chain import Blockchain

from ..models import Ilk, RawEvent, Vault, VaultEventState

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
        vault = Vault.objects.get(
            uid=vault_data["vault_uid"], ilk=vault_data["ilk"]
        )
    except Vault.DoesNotExist:
        return

    latest_position = VaultEventState.objects.filter(
        vault_uid=vault_data["vault_uid"], ilk=vault_data["ilk"]
    ).latest()
    try:
        start_position = (
            VaultEventState.objects.filter(
                vault_uid=vault_data["vault_uid"],
                ilk=vault_data["ilk"],
                timestamp__lte=time_diff,
            ).latest()
        )
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


def get_event_states_for_uid(uid, start_block=None):
    event_states = []
    block_filter = {}

    if start_block:
        block_filter["block_number__gt"] = start_block

    events = RawEvent.objects.filter(vault_uid=uid, **block_filter).values(
        "block_number",
        "timestamp",
        "tx_hash",
        "ilk",
        "operation",
        "collateral",
        "principal",
        "fees",
        "osm_price",
        "rate",
    )
    block_number = 0
    timestamp = 0
    tx_hash = ""
    ilk = ""
    operation = ""
    collateral = 0
    principal = 0
    fees = 0
    osm_price = 0
    rate = 0
    for event in events:
        event_operation = event["operation"]
        if block_number == 0:
            block_number = event["block_number"]
            operation = event["operation"]
            collateral = event["collateral"]
            principal = event["principal"]
            fees = event["fees"]
            osm_price = event["osm_price"]
            timestamp = event["timestamp"]
            tx_hash = event["tx_hash"]
            ilk = event["ilk"]
            rate = event["rate"]
        elif block_number == event["block_number"]:
            block_number = event["block_number"]
            event_operation = event["operation"]
            operations = operation.split("-")
            if event_operation not in operations:
                operations.append(event_operation)
                operations.sort()
                operation = "-".join(operations)
            collateral += event["collateral"]
            principal += event["principal"]
            fees += event["fees"]
            osm_price = event["osm_price"]
            timestamp = event["timestamp"]
            tx_hash = event["tx_hash"]
            ilk = event["ilk"]
            rate = event["rate"]
        else:
            event_states.append(
                VaultEventState(
                    vault_uid=uid,
                    block_number=block_number,
                    timestamp=timestamp,
                    tx_hash=tx_hash,
                    ilk=ilk,
                    operation=operation,
                    collateral=collateral,
                    principal=principal,
                    fees=fees,
                    osm_price=osm_price,
                    rate=rate,
                )
            )
            block_number = event["block_number"]
            event_operation = event["operation"]
            operation = event["operation"]
            collateral = event["collateral"]
            principal = event["principal"]
            fees = event["fees"]
            osm_price = event["osm_price"]
            timestamp = event["timestamp"]
            tx_hash = event["tx_hash"]
            ilk = event["ilk"]
            rate = event["rate"]
    event_states.append(
        VaultEventState(
            vault_uid=uid,
            block_number=block_number,
            timestamp=timestamp,
            tx_hash=tx_hash,
            ilk=ilk,
            operation=operation,
            collateral=collateral,
            principal=principal,
            fees=fees,
            osm_price=osm_price,
            rate=rate,
        )
    )
    return event_states
