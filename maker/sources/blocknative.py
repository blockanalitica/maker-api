# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.conf import settings

from maker.utils.http import retry_get_json


def fetch_gas_prices():
    headers = {"Authorization": settings.BLOCKNATIVE_API_KEY}
    response_data = retry_get_json(
        "https://api.blocknative.com/gasprices/blockprices",
        headers=headers,
        backoff_factor=1,
        respect_retry_after_header=False,
    )

    estimated_prices = response_data["blockPrices"][0]["estimatedPrices"]

    data = {}
    for estimated_price in estimated_prices:
        price = estimated_price["price"] * 10**9
        if estimated_price["confidence"] == 99:
            data["rapid"] = price
        elif estimated_price["confidence"] == 95:
            data["fast"] = price
        elif estimated_price["confidence"] == 80:
            data["standard"] = price
        elif estimated_price["confidence"] == 70:
            data["slow"] = price

    if len(data.keys()) < 4:
        raise KeyError("We need to have all 4 keys!")

    return data
