# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging

from django.conf import settings

from maker.utils.http import requests_retry_session, retry_get_json

log = logging.getLogger(__name__)


def _cortex_get(url, **kwargs):
    data = retry_get_json(
        url,
        session=requests_retry_session(),
        **kwargs,
    )
    return data


def fetch_cortext_ilk_vaults(ilk):
    next_url = (
        f"{settings.BLOCKANALITICA_CORTEX_URL}/"
        f"api/v1/maker/vaults/current-state?ilk={ilk}&page_size=5000"
    )
    while next_url is not None:
        data = _cortex_get(next_url)
        if data["next_page_uri"]:
            next_url = data["next_page_uri"]
        else:
            next_url = None

        for vault in data["results"]:
            yield vault
