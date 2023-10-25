# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

from django_bulk_load import bulk_insert_models, bulk_update_models

from maker.sources.cortex import fetch_cortex_urn_states

# from maker.modules.vaults import save_vault_changes
from maker.utils.metrics import auto_named_statsd_timer
from maker.utils.utils import calculate_rate

from ..models import OSM, Ilk, RawEvent, UrnEventState, Vault, VaultEventState
from ..sources.dicu import MCDSnowflake


def to_human_operation(value):
    label = ""
    if value in ["DEPOSIT-GENERATE-OPEN-PAYBACK", "DEPOSIT-GENERATE-OPEN-WITHDRAW"]:
        label = "SAI Migration"
    elif value == "DEPOSIT-GENERATE":
        label = "Boost"
    elif value == "PAYBACK-WITHDRAW":
        label = "Repay"
    else:
        operations = value.split("-")
        if "OPEN" in operations:
            operations = ["Open"]
        elif "DEPOSIT" in operations and "GENERATE" in operations:
            operations.remove("DEPOSIT")
            operations.remove("GENERATE")
            operations.append("Boost")
        elif "PAYBACK" in operations and "WITHDRAW" in operations:
            operations.remove("PAYBACK")
            operations.remove("WITHDRAW")
            operations.append("Repay")
        for i in range(len(operations)):
            operations[i] = (operations[i].lower()).capitalize()

        label = " / ".join(operations)
    return label


@auto_named_statsd_timer
def save_events():
    try:
        from_block = RawEvent.objects.latest().block_number
    except RawEvent.DoesNotExist:
        from_block = None
    snowflake = MCDSnowflake()
    if from_block:
        query = snowflake.run_query(
            """
                select
                    LOAD_ID,
                    ORDER_INDEX,
                    BLOCK,
                    TIMESTAMP,
                    TX_HASH,
                    VAULT,
                    ILK,
                    OPERATION,
                    DCOLLATERAL,
                    DPRINCIPAL,
                    DFEES,
                    MKT_PRICE,
                    OSM_PRICE,
                    DART,
                    RATE
                from
                    "MCD_VAULTS"."PUBLIC"."VAULTS"
                where BLOCK > {}
            """.format(
                from_block
            )
        )
    else:
        query = snowflake.run_query(
            """
                select
                    LOAD_ID,
                    ORDER_INDEX,
                    BLOCK,
                    TIMESTAMP,
                    TX_HASH,
                    VAULT,
                    ILK,
                    OPERATION,
                    DCOLLATERAL,
                    DPRINCIPAL,
                    DFEES,
                    MKT_PRICE,
                    OSM_PRICE,
                    DART,
                    RATE
                from
                    "MCD_VAULTS"."PUBLIC"."VAULTS"
            """
        )

    events = query.fetchmany(size=1000)
    while len(events) > 0:
        bulk_create = []
        for event in events:
            item = {
                "block_number": event[2],
                "timestamp": event[3].timestamp(),
                "datetime": event[3],
                "tx_hash": event[4],
                "vault_uid": event[5],
                "ilk": event[6],
                "operation": event[7],
                "collateral": event[8],
                "principal": event[9],
                "fees": event[10],
                "mkt_price": event[11],
                "osm_price": event[12],
                "art": event[13],
                "rate": event[14],
                "index": event[1],
            }
            bulk_create.append(RawEvent(**item))
        bulk_insert_models(bulk_create, ignore_conflicts=True)
        events = query.fetchmany(size=1000)
    snowflake.close()


def sync_vault_event_states():
    try:
        block_number = VaultEventState.objects.latest().block_number
    except VaultEventState.DoesNotExist:
        block_number = 0
    bulk_create = []
    bulk_update_vault = []
    vaults = []
    uids = (
        RawEvent.objects.filter(block_number__gt=block_number)
        .order_by("vault_uid")
        .distinct("vault_uid")
        .values_list("vault_uid", flat=True)
    )
    for uid in uids:
        event_states = get_event_states_for_uid(uid, start_block=block_number)
        bulk_create.extend(event_states)
        event = RawEvent.objects.filter(vault_uid=uid).latest()
        bulk_update_vault.append(Vault(uid=uid, last_activity=event.datetime))
        vaults.append({"vault_uid": uid, "ilk": event.ilk})
    if bulk_create:
        bulk_insert_models(bulk_create, ignore_conflicts=True)
    if bulk_update_vault:
        bulk_update_models(
            bulk_update_vault,
            update_field_names=[
                "last_activity",
            ],
            pk_field_names=["uid"],
        )
    sync_vault_event_balances(block_number)
    # if vaults:
    #     for vault_data in vaults:
    #         save_vault_changes(vault_data, 1)
    #         save_vault_changes(vault_data, 7)
    #         save_vault_changes(vault_data, 30)


def save_last_activity(ilk):
    for vault in Vault.objects.filter(ilk=ilk, last_activity=None):
        try:
            event = RawEvent.objects.filter(vault_uid=vault.uid).latest()
            vault.last_activity = event.datetime
            vault.save()
        except RawEvent.DoesNotExist:
            pass


def get_event_states_for_uid(uid, start_block=None):
    event_states = []
    block_filter = {}

    if start_block:
        block_filter["block_number__gt"] = start_block

    events = RawEvent.objects.filter(vault_uid=uid, **block_filter).values(
        "block_number",
        "timestamp",
        "datetime",
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
                    datetime=event["datetime"],
                    tx_hash=tx_hash,
                    ilk=ilk,
                    operation=operation,
                    human_operation=to_human_operation(operation),
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
            datetime=event["datetime"],
            tx_hash=tx_hash,
            ilk=ilk,
            operation=operation,
            collateral=collateral,
            principal=principal,
            fees=fees,
            osm_price=osm_price,
            rate=rate,
            human_operation=to_human_operation(operation),
        )
    )
    return event_states


def sync_vault_event_balances(from_block):
    uids = (
        VaultEventState.objects.filter(block_number__gt=from_block)
        .order_by("vault_uid")
        .distinct("vault_uid")
        .values_list("vault_uid", flat=True)
    )
    bulk_update = []
    for uid in uids:
        event_before = (
            VaultEventState.objects.filter(vault_uid=uid, block_number__lte=from_block)
            .order_by("-block_number")
            .first()
        )
        if event_before:
            before_collateral = event_before.after_collateral or 0
            before_principal = event_before.after_principal or 0
            before_ratio = event_before.after_ratio or 0
            before_rate = event_before.rate / Decimal(1e27)
            before_timestamp = event_before.timestamp
        else:
            before_collateral = 0
            before_principal = 0
            before_ratio = 0
            before_rate = 0
            before_timestamp = 0

        events = VaultEventState.objects.filter(
            vault_uid=uid, block_number__gt=from_block
        ).order_by("block_number")

        for event in events:
            after_rate = event.rate / Decimal(1e27)
            if before_rate > 0 and after_rate > 0:
                rate = calculate_rate(
                    before_rate,
                    before_timestamp,
                    after_rate,
                    event.timestamp,
                )
            else:
                rate = 0
            after_collateral = before_collateral + event.collateral
            if abs(after_collateral) < Decimal("0.0000001"):
                # # If after_principal is less than the small number above, take it as
                # dust and set to 0.
                after_collateral = 0

            after_principal = (
                before_principal + before_principal * rate + event.principal
            )
            if event.fees > 0:
                after_principal -= event.fees

            if after_principal < Decimal("0.0000001"):
                # If after_principal is less than the small number above, take it as
                # dust and set to 0. Otherwise we end up with massive ratio numbers
                after_principal = 0

            osm_price = event.osm_price
            if (
                "RWA" in event.ilk
                or "PSM" in event.ilk
                or "DIRECT" in event.ilk
                or "TELEPORT" in event.ilk
            ):
                osm_price = 1
            if not osm_price:
                ilk_obj = Ilk.objects.get(ilk=event.ilk)
                osm_price = (
                    OSM.objects.filter(symbol=ilk_obj.collateral).latest().current_price
                )
            if before_collateral > 0 and before_principal > 0:
                before_ratio = round(
                    ((before_collateral * osm_price) / before_principal * 100),
                    3,
                )
            else:
                before_ratio = 0
            if after_collateral > 0 and after_principal > 0:
                after_ratio = round(
                    ((after_collateral * osm_price) / after_principal * 100),
                    3,
                )
            else:
                after_ratio = 0
            event.before_collateral = before_collateral
            event.after_collateral = after_collateral
            event.before_principal = before_principal
            event.after_principal = after_principal
            event.before_ratio = before_ratio
            event.after_ratio = after_ratio

            event.human_operation = to_human_operation(event.operation)

            bulk_update.append(event)
            before_collateral = after_collateral
            before_principal = after_principal
            before_rate = after_rate
            before_timestamp = event.timestamp
    bulk_update_models(
        bulk_update,
        update_field_names=[
            "before_collateral",
            "after_collateral",
            "before_principal",
            "after_principal",
            "before_ratio",
            "after_ratio",
            "human_operation",
        ],
        pk_field_names=["id"],
    )


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
