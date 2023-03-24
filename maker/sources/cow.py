# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

import requests

log = logging.getLogger(__name__)


def get_cow_quote(from_token_address, to_token_address, amount):
    data = {
        "sellToken": from_token_address,
        "buyToken": to_token_address,
        # From is not used in what we're doing but is required in the API
        "from": from_token_address,
        "kind": "sell",
        "sellAmountBeforeFee": str(amount),
    }

    url = "https://api.cow.fi/mainnet/api/v1/quote"
    response = requests.post(url, json=data)
    response.raise_for_status()

    return response.json()["quote"]
