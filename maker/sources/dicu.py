# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import requests
from django.conf import settings
from django.core.cache import cache
from oauthlib.oauth2 import LegacyApplicationClient
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from requests_oauthlib import OAuth2Session
from snowflake import connector

DATA_API_URL = "https://data-api.makerdao.network/v1"


def mcd_api_session():
    cache_key = "MCDApi.token"
    token = cache.get(cache_key)
    session = OAuth2Session(
        client=LegacyApplicationClient(client_id=settings.MCDSTATE_API_CLIENT_ID),
        token=token,
    )
    if not token:
        session.token = session.fetch_token(
            token_url="{}/login/access-token".format(DATA_API_URL),
            username=settings.MCDSTATE_API_USERNAME,
            password=settings.MCDSTATE_API_PASSWORD,
        )
        # Access token is valid for 60 minutes, so we're caching for 58 just to make
        # sure we minimise of getting expired errors, while not giving too much thought
        # about automatically refreshing the token
        cache.set(cache_key, session.token, timeout=60 * 58)

    retries = 4
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504, 524),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_last_block_updated():
    client = mcd_api_session()
    url = "{}/state/last_block".format(DATA_API_URL)
    response = client.get(url)
    data = response.json()
    return data["last_block"]


def get_vaults_list(ilk):
    client = mcd_api_session()
    url = "{}/vaults/current_state".format(DATA_API_URL)
    page_size = 1000
    skip = 0
    vaults = []
    while True:
        params = {
            "ilk": ilk,
            "debt_gt": 0,
            "skip": skip,
            "limit": page_size,
        }
        response = client.get(url, params=params)
        response.raise_for_status()

        data = response.json()

        for vault in data:
            vault["collateralization"] = (
                (vault["collateral"] * vault["osm_price"]) / vault["debt"]
            ) * 100

        vaults.extend(data)
        skip += page_size
        if len(data) != page_size:
            break
    return vaults


def get_auctions_for_ilk(ilk, from_datetime=None):
    client = mcd_api_session()
    url = "{}/vaults/liquidations/auctions".format(DATA_API_URL)

    page_size = 500
    skip = 0
    while True:
        params = {
            "ilk": ilk,
            "skip": skip,
            "limit": page_size,
        }
        if from_datetime:
            params["auction_start_gt"] = from_datetime
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            break

        for auction in data:
            yield auction

        skip += page_size


def get_all_actions_for_ilk(ilk):
    client = mcd_api_session()
    url = "{}/vaults/liquidations/actions".format(DATA_API_URL)

    page_size = 500
    skip = 0
    while True:
        params = {
            "ilk": ilk,
            "skip": skip,
            "limit": page_size,
        }
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            break

        for action in data:
            yield action

        skip += page_size


def get_actions_for_auction(ilk, uid):
    client = mcd_api_session()
    url = "{}/vaults/liquidations/actions".format(DATA_API_URL)
    params = {
        "ilk": ilk,
        "auction_id": uid,
    }
    response = client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data


def get_barks_for_ilk(ilk):
    client = mcd_api_session()
    url = "{}/vaults/liquidations/barks".format(DATA_API_URL)

    page_size = 500
    skip = 0
    while True:
        params = {
            "ilk": ilk,
            "skip": skip,
            "limit": page_size,
        }
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not data:
            break

        for action in data:
            yield action

        skip += page_size


def register_user():
    """Registers with MCDState's new API."""
    url = "{}/users/register".format(DATA_API_URL)
    data = {
        "email": settings.MCDSTATE_API_USERNAME,
        "password": settings.MCDSTATE_API_PASSWORD,
    }
    response = requests.post(url, json=data)
    response.raise_for_status()
    print(response.json())


class MCDSnowflake:
    def __init__(self):
        super().__init__()
        self.connection = connector.connect(
            user=settings.MCDSTATE_SNOWFLAKE_USER,
            password=settings.MCDSTATE_SNOWFLAKE_PASSWORD,
            account=settings.MCDSTATE_SNOWFLAKE_ACCOUNT,
            role=settings.MCDSTATE_SNOWFLAKE_ROLE,
            warehouse=settings.MCDSTATE_SNOWFLAKE_WAREHOUSE,
            database=settings.MCDSTATE_SNOWFLAKE_DATABASE,
            schema=settings.MCDSTATE_SNOWFLAKE_SCHEMA,
        )
        self.cursor = self.connection.cursor()

    def run_query(self, sql_query):
        return self.cursor.execute(
            sql_query, timeout=settings.MCDSTATE_SNOWFLAKE_EXECUTE_TIMEOUT
        )

    def query_to_pandas(self, sql_query):
        df = self.run_query(sql_query).fetch_pandas_all()
        df.columns = df.columns.str.lower()
        return df

    def close(self):
        self.cursor.close()
        self.connection.close()


def get_last_block_for_vaults():
    snowflake = MCDSnowflake()
    query = snowflake.run_query(
        """
        select LAST_BLOCK
        from
            "MCD_VAULTS"."PUBLIC"."CURRENT_VAULTS"
        limit 1
        """
    )

    last_block = query.fetchone()
    snowflake.close()
    if last_block:
        return last_block[0]
    else:
        return None


def get_vaults_data(ilk):
    snowflake = MCDSnowflake()
    query = snowflake.run_query(
        """
        select
            VAULT,
            ILK,
            COLLATERAL,
            PRINCIPAL,
            PAID_FEES,
            DEBT,
            ACCRUED_FEES,
            COLLATERALIZATION,
            OSM_PRICE,
            MKT_PRICE,
            RATIO,
            LIQUIDATION_PRICE,
            AVAILABLE_DEBT,
            AVAILABLE_COLLATERAL,
            OWNER,
            DS_PROXY,
            URN,
            ART,
            BLOCK_CREATED,
            TIME_CREATED,
            LAST_BLOCK,
            LAST_TIME
        from
            "MCD_VAULTS"."PUBLIC"."CURRENT_VAULTS"
        WHERE ILK = '{}'
        """.format(
            ilk
        )
    )
    vaults = query.fetchmany(size=1000)
    while len(vaults) > 0:
        for vault in vaults:
            item = {
                "uid": vault[0],
                "ilk": vault[1],
                "collateral": vault[2],
                "principal": vault[3],
                "paid_fees": vault[4],
                "debt": vault[5],
                "accrued_fees": vault[6],
                "collateralization": vault[7],
                "osm_price": vault[8],
                "mkt_price": vault[9],
                "ratio": vault[10],
                "liquidation_price": vault[11],
                "available_debt": vault[12],
                "available_collateral": vault[13],
                "owner": vault[14],
                "ds_proxy": vault[15],
                "urn": vault[16],
                "art": vault[17],
                "block_created": vault[18],
                "time_created": vault[19],
                "last_block": vault[20],
                "last_time": vault[21],
            }
            yield item
        vaults = query.fetchmany(size=1000)
    snowflake.close()
