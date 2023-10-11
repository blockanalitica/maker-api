# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
import logging

from django.conf import settings

from maker.utils.http import requests_retry_session, retry_get_json

log = logging.getLogger(__name__)

SESSIONS = {"papi": requests_retry_session(), "datalake": requests_retry_session()}


def _datalake_get(url, **kwargs):
    data = retry_get_json(
        "{}/{}".format(settings.BLOCKANALITICA_DATALAKE_URL, url.lstrip("/")),
        session=SESSIONS["datalake"],
        **kwargs,
    )
    return data


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


def fetch_compound_historic_rate(symbol, days_ago):
    return _datalake_get(
        "/compound/v2/ethereum/markets/{}/historic-details/?days_ago={}".format(
            symbol, days_ago
        )
    )


def fetch_aave_rates(symbol, days_ago=None):
    return _datalake_get(
        "/aave/v2/ethereum/maker/{}/rates/?days_ago={}".format(symbol, days_ago)
    )


def fetch_compound_rates(symbol, days_ago=None):
    return _datalake_get(
        "/compound/v2/ethereum/maker/{}/rates/?days_ago={}".format(symbol, days_ago)
    )

def fetch_slippage_daily(symbol, date):
    return _datalake_get(
        f"/slippage/{symbol}/{date}"
    )