# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

from eth_utils import to_checksum_address

from maker.models import D3M
from maker.utils.blockchain.chain import Blockchain
from maker.utils.http import retry_get_json

from .helper import get_d3m_contract_data


def get_current_balance(balance_contract):
    chain = Blockchain()
    contract = chain.get_contract(
        "0x4dedf26112b3ec8ec46e7e31ea5e123490b05b8b", abi_type="erc20"
    )
    data = contract.caller.balanceOf(to_checksum_address(balance_contract))
    return round(Decimal(data) / Decimal(1e18), 2)


def get_current_debt():
    chain = Blockchain()
    contract = chain.get_contract("0xf705d2B7e92B3F38e6ae7afaDAA2fEE110fE5914")
    data = contract.caller.totalSupply()
    return round(Decimal(data) / Decimal(1e18), 2)


def save_d3m():
    ilk = "DIRECT-SPARK-DAI"
    data = get_d3m_contract_data(ilk)
    dt = datetime.now()
    balance = get_current_debt()
    D3M.objects.create(
        timestamp=dt.timestamp(),
        datetime=dt,
        protocol="spark",
        ilk=ilk,
        balance=balance,
        **data,
    )


def get_d3m_earnings():
    url = "https://spark-api.blockanalitica.com/v1/ethereum/treasury/ddm-earnings/"
    data = retry_get_json(url)

    return data["earnings"]


def get_d3m_short_info():
    d3m_data = D3M.objects.filter(protocol="spark").latest()
    debt_balance = get_current_debt()
    utilization = 0
    if d3m_data.max_debt_ceiling:
        utilization = debt_balance / d3m_data.max_debt_ceiling
    earnings = get_d3m_earnings()
    return {
        "protocol": "SPARK",
        "protocol_slug": "spark",
        "balance": debt_balance,
        "max_debt_ceiling": d3m_data.max_debt_ceiling,
        "target_borrow_rate": 0,
        "symbol": "DAI",
        "title": "Spark",
        "utilization": utilization,
        "profit": earnings,
    }
