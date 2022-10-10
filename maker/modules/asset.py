# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import requests

from maker.models import (
    Asset,
    MakerAssetCollateral,
    MakerAssetCollateralDebt,
    MakerAssetDebt,
    MakerAssetDebtCollateral,
)
from maker.modules.vaults import get_ilk_debt
from maker.utils.blockchain.chain import Blockchain
from maker.utils.utils import timestamp_to_full_hour

MAKER_CDP_MANAGER = "0x5ef30b9986345249bc32d8928B7ee64DE9435E39"
DAI_ADDRESS = "0x6b175474e89094c44da98b954eedeac495271d0f"

ILKS = {
    "WETH": ["ETH-A", "ETH-B", "ETH-C"],
    "WBTC": ["WBTC-A", "WBTC-B", "WBTC-C"],
    "stETH": ["WSTETH-A"],
    "MANA": ["MANA-A"],
    "LINK": ["LINK-A"],
    "MATIC": ["MATIC-A"],
    "RENBTC": ["RENBTC-A"],
    "UNI": ["UNI-A"],
    "YFI": ["YFI-A"],
}

ADDRESSES = {
    "WETH": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    "WBTC": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "stETH": "0xae7ab96520de3a18e5e111b5eaab095312d7fe84",
    "MANA": "0x0f5d2fb29fb7d3cfee444a200298f468908cc942",
    "LINK": "0x514910771af9ca656af840dff83e8264ecf986ca",
    "MATIC": "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0",
    "RENBTC": "0xeb4c2781e4eba804ce9a9803c67d0893436bb27d",
    "UNI": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "YFI": "0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e",
}


def _get_asset_contracts():
    response = requests.get("https://chainlog.makerdao.com/api/mainnet/active.json")
    content = response.json()
    addresses = []
    symbols = {}
    for symbol, ilks in ILKS.items():
        s = symbol
        if symbol == "WETH":
            s = "ETH"
        if symbol == "stETH":
            s = "WSTETH"
        underlying_address = content.get(s)
        symbols[underlying_address.lower()] = symbol
        for ilk in ilks:
            key = ilk.replace("-", "_")
            token_address = content.get(f"MCD_JOIN_{key}")
            addresses.append((underlying_address.lower(), token_address.lower()))
    return addresses, symbols


def _get_collateral(chain=None):
    w3 = Blockchain(_web3=chain)
    wallets, symbols = _get_asset_contracts()
    calls = []
    for underlying_address, token_address in wallets:
        calls.append(
            (
                underlying_address,
                ["balanceOf(address)(uint256)", token_address],
                [f"{token_address}::{underlying_address}", None],
            )
        )
    data = w3.call_multicall(calls)

    result = defaultdict(Decimal)

    for key, value in data.items():
        asset_address = key.split("::")[1]
        symbol = symbols.get(asset_address)
        decimals = 18
        if symbol in ["WBTC", "RENBTC"]:
            decimals = 8
        result[symbol] += Decimal(value / 10**decimals)
    return result


def _get_collateral_and_debt_for_assets():
    debt = {}
    total = 0
    collateral = _get_collateral()
    for symbol, ilks in ILKS.items():
        total_debt = 0
        for ilk in ilks:
            amount = get_ilk_debt(ilk)
            total_debt += amount
            total += amount
        debt[symbol] = total_debt
    return {"debt": debt, "collateral": collateral}


def get_asset_total_supplies():
    token_calls = []
    for asset in Asset.objects.all():
        token_calls.append(
            (
                asset.address,
                ["totalSupply()(uint256)"],
                [f"{asset.address}", None],
            )
        )

    w3 = Blockchain()
    data = w3.call_multicall(token_calls)
    return data


def save_assets_systemic_risk():
    timestamp = timestamp_to_full_hour(datetime.now())
    assets = _get_collateral_and_debt_for_assets()
    for symbol, _ in assets["collateral"].items():
        asset = MakerAssetCollateral.objects.create(
            timestamp=timestamp,
            token_address=ADDRESSES.get(symbol).lower(),
            underlying_symbol=symbol,
        )
        price = Asset.objects.get(symbol="DAI").price
        MakerAssetCollateralDebt.objects.create(
            asset=asset,
            timestamp=timestamp,
            token_address=DAI_ADDRESS.lower(),
            underlying_symbol="DAI",
            amount=assets["debt"][symbol],
            price=price,
        )
    asset = MakerAssetDebt.objects.create(
        timestamp=timestamp,
        token_address=DAI_ADDRESS.lower(),
        underlying_symbol="DAI",
    )
    for symbol, _ in assets["debt"].items():
        price_symbol = symbol
        if symbol == "RENBTC":
            price_symbol = "WBTC"
        price = Asset.objects.get(symbol=price_symbol).price
        MakerAssetDebtCollateral.objects.create(
            asset=asset,
            timestamp=timestamp,
            token_address=ADDRESSES.get(symbol).lower(),
            underlying_symbol=symbol,
            amount=assets["collateral"][symbol],
            price=price,
        )
