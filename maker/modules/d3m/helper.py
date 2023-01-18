# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

from eth_utils import to_bytes

from maker.constants import (
    D3M_CONTRACT_ADDRESS,
    MCD_VAT_CONTRACT_ADDRESS,
    MKR_DC_IAM_CONTRACT_ADDRESS,
)
from maker.models import D3M
from maker.modules.block import get_or_save_block
from maker.utils.blockchain.chain import Blockchain


def get_d3m_contract_data(ilk):
    chain = Blockchain()

    # Debt ceiling
    vat_contract = chain.get_contract(MCD_VAT_CONTRACT_ADDRESS)
    data = vat_contract.caller.ilks(to_bytes(text=ilk))
    debt_ceiling = Decimal(data[3]) / 10**45

    # D3M
    d3m_contract = chain.get_contract(D3M_CONTRACT_ADDRESS)
    data = d3m_contract.caller.ilks(to_bytes(text=ilk))
    bar = round((1 + (data[2] / 1e15)) ** (60 * 60 * 24 * 365) - 1, 2)
    balance_contract = data[0].lower()

    dc_iam_contract = chain.get_contract(MKR_DC_IAM_CONTRACT_ADDRESS)
    data = dc_iam_contract.caller.ilks(to_bytes(text=ilk))
    max_debt_ceiling = Decimal(data[0]) / 10**45  # line

    return {
        "debt_ceiling": debt_ceiling,
        "max_debt_ceiling": max_debt_ceiling,
        "target_borrow_rate": bar,
        "block_number": chain.get_latest_block(),
        "balance_contract": balance_contract,
    }


def from_apy_to_apr(apy, num_of_compounds):
    apr = num_of_compounds * ((1 + apy) ** Decimal(str((1 / num_of_compounds))) - 1)
    return apr


def get_target_rate_history(ilk):
    ilk_bytes = to_bytes(text=ilk)
    chain = Blockchain()
    topic1 = "{:<064}".format(ilk_bytes.hex())
    filters = {
        "fromBlock": 16126312,
        "toBlock": "latest",
        "topics": [
            "0x851aa1caf4888170ad8875449d18f0f512fd6deb2a6571ea1a41fb9f95acbcd1",
            f"0x{topic1}",
        ],
    }
    events = chain.eth.get_logs(filters)

    for event in events:
        block = get_or_save_block(event["blockNumber"])
        rate = int(event.data, 16)
        target_borrow_rate = round((1 + (rate / 1e15)) ** (60 * 60 * 24 * 365) - 1, 2)
        if ilk == "DIRECT-AAVEV2-DAI":
            protocol = "aave"
        else:
            protocol = "compound"
        D3M.objects.update_or_create(
            timestamp=block.timestamp,
            datetime=block.datetime,
            block_number=event["blockNumber"],
            ilk=ilk,
            protocol=protocol,
            defaults=dict(target_borrow_rate=target_borrow_rate),
        )
