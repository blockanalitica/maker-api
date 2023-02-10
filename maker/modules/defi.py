# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import time as tm
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytz
import requests
from django.db.models.functions import TruncDay, TruncHour
from django.utils.timezone import make_aware

from maker.constants import (
    AWBTC_TOKEN_ADDRESS,
    DAI_TOKEN_ADDRESS,
    WBTC_TOKEN_ADDRESS,
    WETH_TOKEN_ADDRESS,
)
from maker.models import DEFILocked, IlkHistoricParams, Rates
from maker.sources.blockanalitica import fetch_aave_rates, fetch_compound_rates
from maker.utils.blockchain.chain import Blockchain
from maker.utils.utils import timestamp_to_full_hour


def get_aave_rates(underlying_symbol, days_ago=1):
    rates = fetch_aave_rates(underlying_symbol, days_ago=days_ago)
    rates_mapping = defaultdict(dict)
    for rate in rates:
        rates_mapping[rate["dt"]][rate["underlying_symbol"]] = {
            "supply_rate": rate["supply_rate"],
            "borrow_rate": rate["borrow_rate"],
        }
    return rates_mapping


def save_rates_for_aave(underlying_symbol, days_ago=1):
    dt = datetime.fromtimestamp(timestamp_to_full_hour(datetime.now()))
    rates_mapping = get_aave_rates(underlying_symbol, days_ago=days_ago)
    for dt, rates in rates_mapping.items():
        if not rates.get("WETH") or not rates.get(underlying_symbol):
            continue
        Rates.objects.get_or_create(
            datetime=dt,
            symbol=underlying_symbol,
            protocol="aave",
            defaults=dict(
                eth_rate=rates["WETH"]["supply_rate"],
                eth_reward_rate=0,
                borrow_rate=rates[underlying_symbol]["borrow_rate"],
                rewards_rate=0,
            ),
        )


def get_compound_rates(underlying_symbol, days_ago=1):
    rates = fetch_compound_rates(underlying_symbol, days_ago=days_ago)
    rates_mapping = defaultdict(dict)
    for rate in rates:
        rates_mapping[rate["dt"]][rate["underlying_symbol"]] = {
            "supply_rate": rate["supply_rate"],
            "borrow_rate": rate["borrow_rate"],
            "supply_reward_rate": rate["supply_reward_rate"],
            "borrow_reward_rate": rate["borrow_reward_rate"],
        }
    return rates_mapping


def save_rates_for_comp(underlying_symbol):
    dt = datetime.fromtimestamp(timestamp_to_full_hour(datetime.now()))
    rates_mapping = get_compound_rates(underlying_symbol, days_ago=1)

    for dt, rates in rates_mapping.items():
        if not rates.get("WETH") or not rates.get(underlying_symbol):
            continue
        Rates.objects.get_or_create(
            datetime=dt,
            symbol=underlying_symbol,
            protocol="compound",
            defaults=dict(
                eth_rate=rates["WETH"]["supply_rate"],
                eth_reward_rate=rates["WETH"]["supply_reward_rate"],
                borrow_rate=rates[underlying_symbol]["borrow_rate"],
                rewards_rate=rates[underlying_symbol]["borrow_reward_rate"],
            ),
        )


def save_rates_for_maker():
    dt = datetime.fromtimestamp(timestamp_to_full_hour(datetime.now()))
    rate = IlkHistoricParams.objects.filter(ilk="ETH-A", type="stability_fee").latest()
    Rates.objects.get_or_create(
        datetime=dt,
        symbol="DAI",
        protocol="maker",
        defaults=dict(
            eth_rate=0,
            eth_reward_rate=0,
            borrow_rate=rate.stability_fee,
            rewards_rate=0,
        ),
    )


def get_rates(symbol, days_ago=30):
    dt = datetime.now() - timedelta(days=days_ago)
    if days_ago <= 30:
        trunc = TruncHour("datetime")
    else:
        trunc = TruncDay("datetime")
    aave_rates = (
        Rates.objects.annotate(dt=trunc)
        .filter(datetime__gte=dt, symbol=symbol, protocol="aave")
        .order_by("dt", "-datetime")
        .distinct("dt")
        .values(
            "dt",
            "symbol",
            "eth_rate",
            "eth_reward_rate",
            "borrow_rate",
            "rewards_rate",
            "protocol",
            "datetime",
        )
    )
    comp_rates = (
        Rates.objects.annotate(dt=trunc)
        .filter(datetime__gte=dt, symbol=symbol, protocol="compound")
        .order_by("dt", "-datetime")
        .distinct("dt")
        .values(
            "dt",
            "symbol",
            "eth_rate",
            "eth_reward_rate",
            "borrow_rate",
            "rewards_rate",
            "protocol",
            "datetime",
        )
    )

    maker_rates = (
        Rates.objects.annotate(dt=trunc)
        .filter(datetime__gte=dt, symbol=symbol, protocol="maker")
        .order_by("dt", "-datetime")
        .distinct("dt")
        .values(
            "dt",
            "symbol",
            "eth_rate",
            "eth_reward_rate",
            "borrow_rate",
            "rewards_rate",
            "protocol",
            "datetime",
        )
    )

    return list(aave_rates) + list(comp_rates) + list(maker_rates)


def get_current_rate(underlying_symbol, protocol, days_ago):
    if protocol == "aave":
        protocol = "AAVE"
        rates_mapping = get_aave_rates(underlying_symbol, days_ago=days_ago)
    elif protocol == "compound":
        protocol = "COMP"
        rates_mapping = get_compound_rates(underlying_symbol, days_ago=days_ago)

    rates = []
    for dt, values in rates_mapping.items():
        if values.get(underlying_symbol) and values.get("WETH"):
            values["datetime"] = dt
            rates.append(values)

    old = rates[0]
    new = rates[-1]

    supply_rate = new[underlying_symbol]["supply_rate"]
    supply_reward_rate = new[underlying_symbol].get("supply_reward_rate", 0)
    supply_net_rate = supply_rate + supply_reward_rate

    borrow_rate = new[underlying_symbol]["borrow_rate"]
    borrow_reward_rate = new[underlying_symbol].get("borrow_reward_rate", 0)
    borrow_net_rate = borrow_rate - borrow_reward_rate

    old_supply_rate = old[underlying_symbol]["supply_rate"]
    old_supply_reward_rate = old[underlying_symbol].get("supply_reward_rate", 0)
    old_supply_net_rate = old_supply_rate + old_supply_reward_rate

    old_borrow_rate = old[underlying_symbol]["borrow_rate"]
    old_borrow_reward_rate = old[underlying_symbol].get("borrow_reward_rate", 0)
    old_borrow_net_rate = old_borrow_rate - old_borrow_reward_rate
    item = {
        "protocol": protocol,
        "supply_rate": supply_rate,
        "supply_reward_rate": supply_reward_rate,
        "supply_net_rate": supply_net_rate,
        "borrow_rate": borrow_rate,
        "borrow_reward_rate": borrow_reward_rate,
        "borrow_net_rate": borrow_net_rate,
        "real_rate": borrow_rate - 2 * new["WETH"]["supply_rate"],
        "eth_rate": new["WETH"]["supply_rate"],
        "change": {
            "supply_rate": old_supply_rate,
            "supply_reward_rate": old_supply_reward_rate,
            "supply_net_rate": old_supply_net_rate,
            "borrow_rate": old_borrow_rate,
            "borrow_reward_rate": old_borrow_reward_rate,
            "borrow_net_rate": old_borrow_net_rate,
            "real_rate": old_borrow_rate - 2 * old["WETH"]["supply_rate"],
            "eth_rate": old["WETH"]["supply_rate"],
        },
    }
    return item


def get_current_rates(symbol, days_ago=30):
    rates = []

    aave_details = get_current_rate(symbol, "aave", days_ago)
    rates.append(aave_details)

    comp_details = get_current_rate(symbol, "compound", days_ago)
    rates.append(comp_details)

    if symbol == "DAI":
        dt = datetime.now() - timedelta(days=days_ago)
        details = IlkHistoricParams.objects.filter(
            ilk="ETH-A", type="stability_fee"
        ).latest()
        old_details = IlkHistoricParams.objects.filter(
            ilk="ETH-A", type="stability_fee", timestamp__lte=dt.timestamp()
        ).latest()

        item = {
            "protocol": "MKR",
            "supply_rate": 0,
            "supply_reward_rate": 0,
            "supply_net_rate": 0,
            "borrow_rate": details.stability_fee,
            "borrow_reward_rate": 0,
            "borrow_net_rate": details.stability_fee,
            "real_rate": details.stability_fee,
            "eth_rate": 0,
            "change": {
                "supply_rate": 0,
                "supply_reward_rate": 0,
                "supply_net_rate": 0,
                "borrow_rate": old_details.stability_fee,
                "borrow_reward_rate": 0,
                "borrow_net_rate": old_details.stability_fee,
                "real_rate": old_details.stability_fee,
                "eth_rate": 0,
            },
        }
        rates.append(item)

    return rates


def save_rates_for_protocols():
    save_rates_for_aave("DAI")
    save_rates_for_aave("USDC")
    save_rates_for_comp("DAI")
    save_rates_for_comp("USDC")
    save_rates_for_maker()


def convert_wei_to_decimal(value):
    return Decimal(value) / Decimal(10**18)


def _save_balance(balance, asset_symbol, protocol, dt=None):
    if not dt:
        dt = datetime.now()
    DEFILocked.objects.create(
        protocol=protocol,
        underlying_symbol=asset_symbol,
        date=dt.date(),
        datetime=dt,
        timestamp=dt.timestamp(),
        balance=balance,
    )


def fetch_maker_balances(chain, block_number=None):
    protocol = "maker"

    wallets = [
        "0x2F0b23f53734252Bda2277357e97e1517d6B042A",
        "0x08638eF1A205bE6762A8b935F5da9b700Cf7322c",
        "0xF04a5cC80B1E94C69B48f5ee68a08CD2F09A7c3E",
    ]
    balance = Decimal("0")
    for wallet_address in wallets:
        balance += chain.get_balance_of(WETH_TOKEN_ADDRESS, wallet_address)
    _save_balance(convert_wei_to_decimal(balance), "WETH", protocol)

    wallets = [
        "0xBF72Da2Bd84c5170618Fbe5914B0ECA9638d5eb5",
        "0xfA8c996e158B80D77FbD0082BB437556A65B96E0",
        "0x7f62f9592b823331E012D3c5DdF2A7714CfB9de2",
    ]
    balance = Decimal("0")
    for wallet_address in wallets:
        balance += chain.get_balance_of(WBTC_TOKEN_ADDRESS, wallet_address)
    _save_balance(balance / 10**8, "WBTC", protocol)


def fetch_aave2_balances(chain, block_number=None):
    protocol = "aaveV2"

    balance = chain.get_balance_of(
        WETH_TOKEN_ADDRESS, "0x030bA81f1c18d280636F32af80b9AAd02Cf0854e"
    )
    _save_balance(convert_wei_to_decimal(balance), "WETH", protocol)

    balance = chain.get_balance_of(WBTC_TOKEN_ADDRESS, AWBTC_TOKEN_ADDRESS)
    _save_balance(balance / 10**8, "WBTC", protocol)

    balance = chain.get_balance_of(
        DAI_TOKEN_ADDRESS, "0x028171bCA77440897B824Ca71D1c56caC55b68A3"
    )
    _save_balance(convert_wei_to_decimal(balance), "DAI", protocol)


def fetch_comp_balances(chain, block_number=None):
    protocol = "compound"

    balance = chain.eth.get_balance("0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5")
    _save_balance(convert_wei_to_decimal(balance), "WETH", protocol)

    wallets = [
        "0xccF4429DB6322D5C611ee964527D42E5d685DD6a",
        "0xC11b1268C1A384e55C48c2391d8d480264A3A7F4",
    ]
    balance = Decimal("0")
    for wallet_address in wallets:
        balance += chain.get_balance_of(WBTC_TOKEN_ADDRESS, wallet_address)
    _save_balance(balance / 10**8, "WBTC", protocol)

    balance = chain.get_balance_of(
        DAI_TOKEN_ADDRESS, "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643"
    )
    _save_balance(convert_wei_to_decimal(balance), "DAI", protocol)


def fetch_alchemix_balances(chain, block_number=None):
    protocol = "alchemix"

    balance = chain.get_balance_of(
        DAI_TOKEN_ADDRESS, "0xeE69BD81Bd056339368c97c4B2837B4Dc4b796E7"
    )
    _save_balance(convert_wei_to_decimal(balance), "DAI", protocol)


def fetch_defi_balance():
    chain = Blockchain()
    fetch_maker_balances(chain)
    fetch_aave2_balances(chain)
    fetch_comp_balances(chain)
    fetch_alchemix_balances(chain)


def run_query(uri, query, statusCode=200):
    response = requests.post(uri, json={"query": query})
    response.raise_for_status()
    # TODO retry if failing
    if response.status_code == statusCode:
        content = response.json()
        if not content.get("data"):
            tm.sleep(5)
            return run_query(uri, query, statusCode=200)
        return response.json()
    else:
        tm.sleep(5)
        return run_query(uri, query, statusCode=200)


URL = "https://api.santiment.net/graphiql"


def fetch_historical_balance(address, slug, date_from, date_to, interval="24h"):
    query = """
        {
          historicalBalance(
            address: "%s"
            slug: "%s"
            from: "%s"
            to: "%s"
            interval: "%s"
          ){
            balance
            datetime
          }
        }
    """ % (
        address,
        slug,
        make_aware(date_from, timezone=pytz.utc).isoformat(),
        make_aware(date_to, timezone=pytz.utc).isoformat(),
        interval,
    )
    response = run_query(URL, query)
    data = []
    for row in response["data"]["historicalBalance"]:
        data.append(
            {
                "datetime": datetime.strptime(row["datetime"], "%Y-%m-%dT%H:%M:%S%z"),
                "balance": Decimal(str(row["balance"])),
            }
        )
    return data


def fetch_historical_defi_balance(wallets, underlying_symbol, protocol):
    key = None
    if underlying_symbol == "WETH":
        key = "weth"
        if protocol == "compound":
            key = "ethereum"
    elif underlying_symbol == "WBTC":
        key = "wrapped-bitcoin"
    elif underlying_symbol == "DAI":
        key = "multi-collateral-dai"
    elif underlying_symbol == "stETH":
        key = "steth"

    last_date = datetime(2019, 11, 11)
    obj = (
        DEFILocked.objects.filter(
            protocol=protocol, underlying_symbol=underlying_symbol
        )
        .order_by("-date")
        .first()
    )
    if obj:
        last_date = datetime.combine(obj.date, time())
    all_balances = defaultdict(int)
    for address in wallets:
        histories = fetch_historical_balance(address, key, last_date, datetime.now())
        for item in histories:
            all_balances[item["datetime"]] += item["balance"]
    items = []

    for dt, balance in all_balances.items():
        if balance == 0:
            continue
        if last_date and dt <= make_aware(last_date):
            continue
        if dt >= make_aware(datetime.combine(date.today(), time())):
            continue
        items.append(
            DEFILocked(
                protocol=protocol,
                underlying_symbol=underlying_symbol,
                date=dt.date(),
                datetime=dt,
                timestamp=dt.timestamp(),
                balance=balance,
            )
        )
    DEFILocked.objects.bulk_create(items)


def backpopulate_tvl():
    protocol = "maker"
    # ETH
    wallets = [
        "0x2F0b23f53734252Bda2277357e97e1517d6B042A",
        "0x08638eF1A205bE6762A8b935F5da9b700Cf7322c",
        "0xF04a5cC80B1E94C69B48f5ee68a08CD2F09A7c3E",
    ]
    fetch_historical_defi_balance(wallets, "WETH", protocol)

    wallets = [
        "0xBF72Da2Bd84c5170618Fbe5914B0ECA9638d5eb5",
        "0xfA8c996e158B80D77FbD0082BB437556A65B96E0",
        "0x7f62f9592b823331E012D3c5DdF2A7714CfB9de2",
    ]
    fetch_historical_defi_balance(wallets, "WBTC", protocol)

    # wallets = [
    #     "0x248cCBf4864221fC0E840F29BB042ad5bFC89B5c",
    #     "0x10CD5fbe1b404B7E19Ef964B63939907bdaf42E2",
    # ]
    # fetch_historical_defi_balance(wallets, "stETH", protocol)

    protocol = "aaveV2"
    wallets = ["0x030bA81f1c18d280636F32af80b9AAd02Cf0854e"]
    fetch_historical_defi_balance(wallets, "WETH", protocol)
    wallets = [AWBTC_TOKEN_ADDRESS]
    fetch_historical_defi_balance(wallets, "WBTC", protocol)
    # wallets = ["0x1982b2f5814301d4e9a8b0201555376e62f82428"]
    # fetch_historical_defi_balance(wallets, "stETH", protocol)

    protocol = "compound"
    wallets = ["0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5"]

    fetch_historical_defi_balance(wallets, "WETH", protocol)
    wallets = [
        "0xccF4429DB6322D5C611ee964527D42E5d685DD6a",
        "0xC11b1268C1A384e55C48c2391d8d480264A3A7F4",
    ]
    fetch_historical_defi_balance(wallets, "WBTC", protocol)
