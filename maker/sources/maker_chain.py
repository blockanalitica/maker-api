# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

from django_bulk_load import bulk_insert_models
from eth_utils import remove_0x_prefix, to_hex
from web3 import Web3

from maker.constants import MCD_JUG_CONTRACT_ADDRESS, MCD_SPOT_CONTRACT_ADDRESS
from maker.models import Ilk, IlkHistoricParams
from maker.modules.block import get_or_save_block
from maker.utils.blockchain.chain import Blockchain


def sync_lr_for_ilk():
    chain = Blockchain()
    bulk_create = []
    for ilk in Ilk.objects.all():
        try:
            last_block = (
                IlkHistoricParams.objects.filter(ilk=ilk.ilk, type="lr")
                .latest()
                .block_number
            )
            from_block = last_block + 1
        except IlkHistoricParams.DoesNotExist:
            from_block = "earliest"

        mat_topic = to_hex(text="mat").ljust(66, "0")
        ilk_topic = to_hex(text=ilk.ilk).ljust(66, "0")
        filters = {
            "fromBlock": from_block,
            "toBlock": "latest",
            "address": MCD_SPOT_CONTRACT_ADDRESS,
            "topics": [None, None, ilk_topic, mat_topic],
        }
        events = chain.eth.get_logs(filters)
        block_numbers = set()
        for event in events:
            block_numbers.add(event["blockNumber"])

        if len(block_numbers) == 0:
            continue

        key = remove_0x_prefix(to_hex(text=ilk.ilk)).ljust(64, "0")
        # https://medium.com/aigang-network/how-to-read-ethereum-contract-storage-44252c8af925
        index = "0000000000000000000000000000000000000000000000000000000000000001"
        position = Web3.keccak(hexstr=key + index).hex()
        # Increase position by 1 to get to the `mat` field aka liquidation ratio
        position = hex(int(position, 16) + 1)

        for block_number in sorted(block_numbers):
            storage = chain.get_storage_at(
                MCD_SPOT_CONTRACT_ADDRESS, position, block_identifier=block_number
            )
            lr = int(Decimal(int(storage, 16)) / 10**27 * 100)
            block = get_or_save_block(block_number)
            bulk_create.append(
                IlkHistoricParams(
                    ilk=ilk.ilk,
                    type="lr",
                    block_number=block_number,
                    timestamp=block.timestamp,
                    lr=lr,
                )
            )

    if bulk_create:
        bulk_insert_models(bulk_create, ignore_conflicts=True)


def sync_stability_fee_for_ilk():
    chain = Blockchain()
    bulk_create = []
    for ilk in Ilk.objects.all():
        try:
            last_block = (
                IlkHistoricParams.objects.filter(ilk=ilk.ilk, type="stability_fee")
                .latest()
                .block_number
            )
            from_block = last_block + 1
        except IlkHistoricParams.DoesNotExist:
            from_block = "earliest"

        duty_topic = to_hex(text="duty").ljust(66, "0")
        ilk_topic = to_hex(text=ilk.ilk).ljust(66, "0")

        filters = {
            "fromBlock": from_block,
            "toBlock": "latest",
            "address": MCD_JUG_CONTRACT_ADDRESS,
            "topics": [None, None, ilk_topic, duty_topic],
        }

        events = chain.eth.get_logs(filters)
        block_numbers = set()
        for event in events:
            block_numbers.add(event["blockNumber"])

        if len(block_numbers) == 0:
            continue

        key = remove_0x_prefix(to_hex(text=ilk.ilk)).ljust(64, "0")
        index = "0000000000000000000000000000000000000000000000000000000000000001"
        position = Web3.keccak(hexstr=key + index).hex()

        for block_number in sorted(block_numbers):
            storage = chain.get_storage_at(
                MCD_JUG_CONTRACT_ADDRESS, position, block_identifier=block_number
            )
            fee = Decimal(int(storage, 16)) / 10**27
            fee = fee ** (60 * 60 * 24 * 365) - 1

            block = get_or_save_block(block_number)
            bulk_create.append(
                IlkHistoricParams(
                    ilk=ilk.ilk,
                    block_number=block_number,
                    timestamp=block.timestamp,
                    type="stability_fee",
                    stability_fee=fee,
                )
            )
    if bulk_create:
        bulk_insert_models(bulk_create, ignore_conflicts=True)
