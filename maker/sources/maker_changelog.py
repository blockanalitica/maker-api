# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import requests


def get_fetch_changelog():
    response = requests.get("https://chainlog.makerdao.com/api/mainnet/active.json")
    content = response.json()
    return content


def get_addresses_for_asset(symbol):
    data = get_fetch_changelog()

    address = data.get(symbol)
    oracle_address = data.get(f"PIP_{symbol}")
    return address, oracle_address
