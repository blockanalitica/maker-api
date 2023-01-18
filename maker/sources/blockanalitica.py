# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging

from django.conf import settings

from maker.utils.http import requests_retry_session, retry_get_json

log = logging.getLogger(__name__)

SESSIONS = {"papi": requests_retry_session(), "datalake": requests_retry_session()}


def _papi_get(url, **kwargs):
    log.debug("Fetching from Papi %s", url, **kwargs)
    data = retry_get_json(
        "{}/{}".format(settings.BLOCKANALITICA_PAPI_URL, url.lstrip("/")),
        session=SESSIONS["papi"],
        **kwargs,
    )
    return data


def _datalake_get(url, **kwargs):
    data = retry_get_json(
        "{}/{}".format(settings.BLOCKANALITICA_DATALAKE_URL, url.lstrip("/")),
        session=SESSIONS["datalake"],
        **kwargs,
    )
    return data


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


def fetch_aave_historic_rate(symbol, days_ago):
    return _datalake_get(
        "/aave/v2/ethereum/markets/{}/historic-details/?days_ago={}".format(
            symbol, days_ago
        )
    )
