# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from maker.utils.http import retry_get_json

log = logging.getLogger(__name__)


def get_oneinch_quote(from_token_address, to_token_address, amount):
    url = (
        f"https://api.1inch.io/v4.1/1/quote?"
        f"fromTokenAddress={from_token_address}"
        f"&toTokenAddress={to_token_address}&amount={amount}"
    )
    return retry_get_json(
        url,
        backoff_factor=1,
        status_forcelist=(400, 429, 500, 502, 503, 504),
        respect_retry_after_header=False,
    )
