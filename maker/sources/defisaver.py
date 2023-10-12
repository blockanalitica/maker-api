# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django_bulk_load import bulk_update_models
from requests.adapters import RetryError

from maker.constants import DEFISAVER_MCD_SUBSCRIBTION_v2
from maker.models import Vault
from maker.utils.blockchain.chain import Blockchain
from maker.utils.http import retry_get_json
from maker.utils.utils import chunks


def fetch_defisaver_vault_data(vault_id):
    url = f"https://defiexplore.com/api/cdps/{vault_id}"
    return retry_get_json(url, raise_for_status=False)


def get_defisaver_vault_data(vault_id):
    try:
        data = fetch_defisaver_vault_data(vault_id)
    except RetryError:
        return None, False
    if not data:
        return None, False
    payload = {}
    data.pop("events", None)
    if not data or data.get("error"):
        return None, False
    payload["collateral"] = Decimal(data["collateral"])
    payload["debt"] = Decimal(data["debt"])
    payload["user_address"] = data["userAddr"]
    payload["collateralization"] = Decimal(data["ratio"]) * 100
    payload["defisaver_protected"] = data["subscribedToAutomation"]
    payload["price"] = data["price"]
    payload["next_price"] = data["futurePrice"]
    if data["liqPrice"] in ["NaN", "Infinity", "0"]:
        return None, True
    if Decimal(data["liqPrice"]) < 0:
        return None, True
    try:
        payload["liquidation_price"] = round(Decimal(data["liqPrice"]), 18)
    except InvalidOperation:
        return None, True
    return payload, False


def get_defisaver_chain_data(ilk):
    w3 = Blockchain()
    protection_bulk_update = []
    all_ids = Vault.objects.filter(ilk=ilk, is_active=True).values_list(
        "uid", flat=True
    )
    for ids in chunks(all_ids, 3000):
        vaults_protected = fetch_protected_vaults(ids, chain=w3)
        for uid, response in vaults_protected.items():
            protection = response["getSubscribedInfo"]
            data = {"uid": uid}
            if protection[0] is True:
                data["protection_service"] = "defisaver"
                protection_bulk_update.append(Vault(**data))
            else:
                data["protection_service"] = None
                protection_bulk_update.append(Vault(**data))
        if protection_bulk_update:
            bulk_update_models(
                protection_bulk_update,
                update_field_names=[
                    "protection_service",
                ],
                pk_field_names=["uid"],
            )
        protection_bulk_update = []


def fetch_protected_vaults(vaults_ids, chain=None):
    w3 = Blockchain(_web3=chain)
    token_calls = []
    for id in vaults_ids:
        try:
            call_id = int(id)
        except ValueError:
            continue

        token_calls.append(
            (
                DEFISAVER_MCD_SUBSCRIBTION_v2,
                [
                    "getSubscribedInfo(uint256)"
                    "((bool,uint128,uint128,uint128,uint128,address,uint256,uint256))",
                    call_id,
                ],
                [f"{id}:getSubscribedInfo", None],
            )
        )
        token_calls.append(
            (
                DEFISAVER_MCD_SUBSCRIBTION_v2,
                [
                    "getOwner(uint256)(address)",
                    call_id,
                ],
                [f"{id}:getOwner", None],
            )
        )
    data = w3.call_multicall(token_calls)

    results = defaultdict(dict)
    for key, values in data.items():
        uid, label = key.split(":")
        results[uid][label] = values
    return results
