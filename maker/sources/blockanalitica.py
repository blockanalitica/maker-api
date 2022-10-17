# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def _papi_get(url, **kwargs):
    log.debug("Fetching from Papi %s", url, **kwargs)
    response = requests.get(
        "{}/{}".format(settings.BLOCKANALITICA_PAPI_URL, url.lstrip("/")), **kwargs
    )
    response.raise_for_status()
    return response.json()


def _datalake_get(url, **kwargs):
    log.debug("Fetching from Datalake %s", url, **kwargs)
    response = requests.get(
        "{}/{}".format(settings.BLOCKANALITICA_DATALAKE_URL, url.lstrip("/")), **kwargs
    )
    response.raise_for_status()
    return response.json()


def fetch_aave_rates(symbol, days_ago=None):
    params = {}
    if days_ago:
        params["days_ago"] = days_ago
    return _papi_get("/aave/defi/rates/{}".format(symbol), params=params)


def fetch_aave_d3m_dai_stats():
    return _papi_get("/aave/defi/d3m/dai-stats/")


def fetch_aave_d3m_dai_historic_rates(days_ago=None):
    params = {}
    if days_ago:
        params["days_ago"] = days_ago
    return _papi_get("/aave/defi/d3m/dai-historic-rates/", params=params)


def fetch_compound_rates(symbol, days_ago=None):
    params = {}
    if days_ago:
        params["days_ago"] = days_ago
    return _papi_get("/compound/defi/rates/{}".format(symbol), params=params)


def fetch_compound_d3m_dai_stats():
    return _papi_get("/compound/defi/d3m/dai-stats/")


def fetch_ilk_vaults(ilk):
    next_url = "/maker/ilks/{}/vaults/?p_size=1000".format(ilk)
    while next_url is not None:
        data = _datalake_get(next_url)
        if data["next"]:
            next_url = "/".join(data["next"].split("/")[3:])
        else:
            next_url = None

        for vault in data["results"]:
            yield vault
