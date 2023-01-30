# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from django.db.models.functions import TruncHour
from eth_utils import to_checksum_address
from web3 import Web3

from maker.models import D3M, SurplusBuffer
from maker.modules.block import get_or_save_block
from maker.sources.blockanalitica import fetch_aave_historic_rate
from maker.utils.blockchain.chain import Blockchain

from .helper import get_d3m_contract_data


def get_target_rate_history():
    """DEPRECATED"""
    chain = Blockchain()
    filters = {
        "fromBlock": 14054075,
        "toBlock": "latest",
        "address": to_checksum_address("0x12F36cdEA3A28C35aC8C6Cc71D9265c17C74A27F"),
        "topics": [
            "0xe986e40cc8c151830d4f61050f4fb2e4add8567caad2d5f5496f9158e91fe4c7"
        ],
    }
    events = chain.eth.get_logs(filters)

    for event in events:
        block = get_or_save_block(event["blockNumber"])
        target_borrow_rate = chain.convert_ray(Web3.toInt(hexstr=event["data"]))
        D3M.objects.update_or_create(
            timestamp=block.timestamp,
            datetime=block.datetime,
            block_number=event["blockNumber"],
            protocol="aave",
            defaults=dict(target_borrow_rate=target_borrow_rate),
        )


def get_current_balance(balance_contract):
    chain = Blockchain()
    contract = chain.get_contract(
        "0x028171bca77440897b824ca71d1c56cac55b68a3", abi_type="erc20"
    )
    data = contract.caller.balanceOf(to_checksum_address(balance_contract))
    return Decimal(data) / Decimal(1e18)


def save_d3m():
    ilk = "DIRECT-AAVEV2-DAI"
    data = get_d3m_contract_data(ilk)
    dt = datetime.now()
    balance = get_current_balance(data["balance_contract"])
    D3M.objects.create(
        timestamp=dt.timestamp(),
        datetime=dt,
        protocol="aave",
        ilk=ilk,
        balance=balance,
        **data,
    )


def get_d3m_short_info():
    d3m_data = D3M.objects.filter(protocol="aave").latest()
    balance = get_current_balance(d3m_data.balance_contract)

    utilization = 0
    if d3m_data.max_debt_ceiling:
        utilization = balance / d3m_data.max_debt_ceiling
    return {
        "protocol": "AAVE",
        "protocol_slug": "aave",
        "balance": balance,
        "max_debt_ceiling": d3m_data.max_debt_ceiling,
        "target_borrow_rate": d3m_data.target_borrow_rate,
        "symbol": "aDAI",
        "title": "Aave",
        "utilization": utilization,
    }


def get_d3m_info():
    ilk = "DIRECT-AAVEV2-DAI"
    d3m_data = D3M.objects.filter(ilk=ilk).latest()
    surplus_buffer = SurplusBuffer.objects.latest().amount
    stats = get_dai_market()
    balance = get_current_balance(d3m_data.balance_contract)
    data = {
        "protocol": "AAVE",
        "protocol_slug": "aave",
        "balance": balance,
        "debt_ceiling": d3m_data.max_debt_ceiling,
        "target_borrow_rate": d3m_data.target_borrow_rate,
        "symbol": "aDAI",
        "title": "Aave",
        "utilization_balance": balance / d3m_data.max_debt_ceiling,
        "surplus_buffer": surplus_buffer,
        "utilization_surplus_buffer": balance / surplus_buffer,
        "supply_utilization": None,
    }

    data.update(stats)
    return data


def get_dai_market():
    data_provider_address = "0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d"
    underlying_address = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
    token_calls = []
    token_calls.append(
        (
            data_provider_address,
            [
                "getReserveData(address)((uint256,uint256,uint256,uint256"
                ",uint256,uint256,uint256,uint256,uint256,uint40))",
                underlying_address,
            ],
            ["getReserveData", None],
        )
    )
    token_calls.append(
        (
            data_provider_address,
            [
                (
                    "getReserveConfigurationData(address)((uint256,uint256,uint256,uint256"
                    ",uint256,bool,bool,bool,bool,bool))"
                ),
                underlying_address,
            ],
            ["getReserveConfigurationData", None],
        )
    )
    token_calls.append(
        (
            data_provider_address,
            [
                ("getReserveTokensAddresses(address)((address,address,address))"),
                underlying_address,
            ],
            ["getReserveTokensAddresses", None],
        )
    )

    w3 = Blockchain()
    data = w3.call_multicall(token_calls)
    item = data["getReserveData"]
    conf_data = data["getReserveConfigurationData"]
    decimals = conf_data[0]
    data["total_supply"] = (item[0] + (item[1] + item[2])) / 10**decimals
    data["total_borrow"] = (item[1] + item[2]) / 10**decimals
    data["supply_rate"] = item[3] / Decimal(10**27)
    data["borrow_rate"] = item[4] / Decimal(10**27)
    data["borrow_stable_rate"] = item[5] / Decimal(10**27)
    data["variable_debt"] = item[2] / 10**decimals
    data["stable_debt"] = item[1] / 10**decimals
    data["utilization"] = data["total_borrow"] / data["total_supply"]
    return data


def get_historic_rates(days_ago=30):
    ilk = "DIRECT-AAVEV2-DAI"
    dt = datetime.now() - timedelta(days=days_ago)
    target_borrow_rates = (
        D3M.objects.filter(ilk=ilk, datetime__gte=dt)
        .annotate(dt=TruncHour("datetime"))
        .values("target_borrow_rate", "dt")
    )
    historic_rates = fetch_aave_historic_rate("DAI", days_ago)

    return {
        "borrow_rates": historic_rates,
        "target_borrow_rates": target_borrow_rates,
    }


RESERVE_FACTOR = 0.1


class D3MAaveCompute:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dai_curve = None
        self._borrow_rate_df_cache = {}
        self._utilization_rate_df_cache = {}
        self._todays_rate = None
        self._defi_rate = None
        self._rates = None
        self._d3m_model = None

    @property
    def d3m_model(self):
        if not self._d3m_model:
            self._d3m_model = D3M.objects.filter(protocol="aave").latest()
        return self._d3m_model

    def get_rates(self):
        if not self._rates:
            rate = get_dai_market()
            self._rates = {
                "borrow_rate": Decimal(str(rate["borrow_rate"])),
                "total_supply": Decimal(str(rate["total_supply"])),
                "total_borrow": Decimal(str(rate["total_borrow"])),
                "borrow_stable_rate": Decimal(str(rate["borrow_stable_rate"])),
                "variable_debt": Decimal(str(rate["variable_debt"])),
                "stable_debt": Decimal(str(rate["stable_debt"])),
            }
        return self._rates

    @property
    def dai_curve(self):
        if not self._dai_curve:
            u_optimal = 0.8
            base = 0
            slope_1 = 0.04
            slope_2 = 0.75

            data = []

            utilization_rates = np.around(
                np.linspace(start=0, stop=1, num=10000, endpoint=True), 4
            )

            for u_rate in utilization_rates:
                if u_rate < u_optimal:
                    borrow_rate = base + (u_rate / u_optimal) * slope_1
                else:
                    borrow_rate = (
                        base
                        + slope_1
                        + ((u_rate - u_optimal) / (1 - u_optimal) * slope_2)
                    )

                data.append(
                    {
                        "utilization_rate": Decimal(str(u_rate)),
                        "borrow_rate": Decimal(str(round(borrow_rate, 4))),
                    }
                )
            self._dai_curve = data
        return self._dai_curve

    def get_utilization_rate_gte(self, value):
        # We call this function many, many times so it's a bit weird for speed purposes
        if not self._borrow_rate_df_cache:
            df = pd.DataFrame.from_dict(self.dai_curve)
            df_chunks = np.array_split(df, 30)
            for chunk in df_chunks:
                self._borrow_rate_df_cache[max(chunk["borrow_rate"])] = chunk

        for max_value, chunk in self._borrow_rate_df_cache.items():
            if value <= max_value:
                return chunk.loc[chunk["borrow_rate"] <= value].iloc[-1][
                    "utilization_rate"
                ]

    def get_borrow_rate_gte(self, value):
        # We call this function many, many times so it's a bit weird for speed purposes
        if not self._utilization_rate_df_cache:
            df = pd.DataFrame.from_dict(self.dai_curve)
            df_chunks = np.array_split(df, 30)
            for chunk in df_chunks:
                self._utilization_rate_df_cache[max(chunk["utilization_rate"])] = chunk

        for max_value, chunk in self._utilization_rate_df_cache.items():
            if value <= max_value:
                return chunk.loc[chunk["utilization_rate"] >= value].iloc[0][
                    "borrow_rate"
                ]

    def compute_metrics(self, target_borrow_rate, d3m_dc, heatmap=False):
        rates = self.get_rates()
        unwind = False
        if not heatmap:
            if target_borrow_rate > rates["borrow_rate"]:
                unwind = True
        old_current_dai = max(0, self.d3m_model.balance)
        if unwind:
            d3m_current_dai = 0
            d3m_dc_additional = max(0, d3m_dc - d3m_current_dai)
            dai_supply = rates["total_supply"] - max(0, self.d3m_model.balance)
            dai_borrow = rates["total_borrow"]
        else:
            d3m_current_dai = max(0, self.d3m_model.balance)
            d3m_dc_additional = max(0, d3m_dc - d3m_current_dai)
            dai_supply = rates["total_supply"]
            dai_borrow = rates["total_borrow"]

        if target_borrow_rate == 0:
            d3m_dc_additional = 0

        average_stable_rate = rates["borrow_stable_rate"]
        share_variable_debt = rates["variable_debt"] / rates["total_borrow"]
        share_stable_debt = rates["stable_debt"] / rates["total_borrow"]

        simulation_dai_borrow = Decimal(int(dai_borrow))

        # extra supply at which given the simulation borrow the borrow rate == target
        # borrow rate minus the existing supply
        d3m_supply_needed = Decimal(
            max(
                int(
                    (
                        simulation_dai_borrow
                        / self.get_utilization_rate_gte(target_borrow_rate)
                    )
                    - dai_supply
                ),
                0,
            ),
        )

        # current supply + D3M exposure capped at DC
        d3m_exposure = min(d3m_dc_additional, d3m_supply_needed)
        simulation_dai_supply = Decimal(int(dai_supply + d3m_exposure))

        simulation_utilization_rate = round(
            simulation_dai_borrow / simulation_dai_supply, 6
        )
        simulation_borrow_rate = round(
            self.get_borrow_rate_gte(simulation_utilization_rate),
            6,
        )

        simulation_supply_rate = round(
            simulation_utilization_rate
            * (
                share_stable_debt * average_stable_rate
                + share_variable_debt * simulation_borrow_rate
            )
            * Decimal(str((1 - RESERVE_FACTOR))),
            6,
        )

        # supply rate if target rate was in effect, assuming the same stable/borrow
        # distribution and average stable rate
        simulation_dai_supply_target = dai_supply + d3m_supply_needed
        simulation_utilization_rate_target = round(
            dai_borrow / simulation_dai_supply_target, 6
        )
        implied_supply_rate = round(
            simulation_utilization_rate_target
            * (
                share_stable_debt * average_stable_rate
                + share_variable_debt * target_borrow_rate
            )
            * Decimal(str((1 - RESERVE_FACTOR))),
            6,
        )

        share_dai_deposits = (d3m_exposure + d3m_current_dai) / simulation_dai_supply
        d3m_revenue_excl_rewards = simulation_supply_rate * min(
            d3m_dc, (d3m_exposure + d3m_current_dai)
        )

        data = {
            "d3m_dc": d3m_dc,
            "target_borrow_rate": target_borrow_rate,
            "simulation_dai_borrow": simulation_dai_borrow,
            "d3m_supply_needed": d3m_supply_needed,
            "d3m_exposure": d3m_exposure,
            "simulation_dai_supply": simulation_dai_supply,
            "simulation_utilization_rate": simulation_utilization_rate,
            "simulation_borrow_rate": simulation_borrow_rate,
            "simulation_supply_rate": simulation_supply_rate,
            "simulation_dai_supply_target": simulation_dai_supply_target,
            "simulation_utilization_rate_target": simulation_utilization_rate_target,
            "implied_supply_rate": implied_supply_rate,
            "share_dai_deposits": share_dai_deposits,
            "d3m_revenue": d3m_revenue_excl_rewards,
            "d3m_balance": d3m_current_dai,
            "d3m_exposure_total": d3m_current_dai + d3m_exposure,
        }

        if unwind:
            data["d3m_exposure_total"] = d3m_exposure
            data["d3m_balance"] = old_current_dai
            data["d3m_exposure"] = d3m_exposure - old_current_dai
        return data
