# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from maker.utils.http import retry_get_json

log = logging.getLogger(__name__)


def get_zerox_quote(from_token_address, to_token_address, amount):
    url = (
        f"https://api.0x.org/swap/v1/quote?"
        f"buyToken={to_token_address}"
        f"&sellToken={from_token_address}&sellAmount={amount}"
    )
    return retry_get_json(url, status_forcelist=(400, 429, 500, 502, 503, 504))
