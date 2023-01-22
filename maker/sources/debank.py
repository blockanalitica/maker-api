# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django.conf import settings

from maker.utils.http import retry_get_json

DEBANK_API_URL = "https://pro-openapi.debank.com/v1/"


def fetch_user_token_list(wallet_address):
    url = f"user/token_list?id={wallet_address}&chain_id=eth&is_all=false"
    data = retry_get_json(
        "{}{}".format(DEBANK_API_URL, url),
        headers={"AccessKey": settings.DEBANK_API_KEY},
    )
    return data
