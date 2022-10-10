# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from maker.utils.http import retry_get_json

log = logging.getLogger(__name__)


API_URL = "https://api.makerburn.com"


def fetch_status():
    return retry_get_json(f"{API_URL}/status")


def get_collateral_list():
    data = fetch_status()
    return data["collateral_list"]
