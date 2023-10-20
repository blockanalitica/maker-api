# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from web3 import Web3
from maker.utils.blockchain.chain import Blockchain


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
