# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

from eth_utils import to_checksum_address

from maker.models import D3M
from maker.utils.blockchain.chain import Blockchain

from .helper import get_d3m_contract_data


def get_current_balance(balance_contract):
    chain = Blockchain()
    contract = chain.get_contract(
        "0x4dedf26112b3ec8ec46e7e31ea5e123490b05b8b", abi_type="erc20"
    )
    data = contract.caller.balanceOf(to_checksum_address(balance_contract))
    return Decimal(data) / Decimal(1e18)


def save_d3m():
    ilk = "DIRECT-SPARK-DAI"
    data = get_d3m_contract_data(ilk)
    dt = datetime.now()
    balance = get_current_balance(data["balance_contract"])
    D3M.objects.create(
        timestamp=dt.timestamp(),
        datetime=dt,
        protocol="spark",
        ilk=ilk,
        balance=balance,
        **data,
    )


def get_d3m_short_info():
    d3m_data = D3M.objects.filter(protocol="spark").latest()
    balance = get_current_balance(d3m_data.balance_contract)

    utilization = 0
    if d3m_data.max_debt_ceiling:
        utilization = balance / d3m_data.max_debt_ceiling
    return {
        "protocol": "SPARK",
        "protocol_slug": "spark",
        "balance": balance,
        "max_debt_ceiling": d3m_data.max_debt_ceiling,
        "target_borrow_rate": 0,
        "symbol": "DAI",
        "title": "Spark",
        "utilization": utilization,
    }
