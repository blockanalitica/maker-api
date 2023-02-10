# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from maker.utils.http import retry_get_json

LLAMA_COINS_API_URL = "https://coins.llama.fi/"


def fetch_current_price(coins):
    url = "prices/current/{}/".format(",".join(coins))
    data = retry_get_json("{}{}".format(LLAMA_COINS_API_URL, url))
    return data["coins"]


def fetch_price_for_timestamp(timestamp, coins):
    url = "prices/historical/{}/{}/".format(timestamp, ",".join(coins))
    data = retry_get_json("{}{}".format(LLAMA_COINS_API_URL, url))
    return data["coins"]
