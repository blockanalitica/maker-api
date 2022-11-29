# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

import numpy as np
import pandas as pd

from maker.utils.blockchain.chain import Blockchain


def get_d3m_short_info():
    return {
        "protocol": "Compound",
        "protocol_slug": "compound",
        "balance": 0,
        "max_debt_ceiling": Decimal("0"),
        "target_borrow_rate": Decimal("0"),
        "symbol": "cDAI",
        "title": "Compound",
        "utilization": 0,
        "pending": True,
    }


def get_d3m_info():
    data = get_d3m_short_info()
    stats = get_compound_dai_market()
    data.update(stats)
    return data


RESERVE_FACTOR = 0.15
BLOCKS_PER_YEAR = 2407328


def from_apy_to_apr(apy, num_of_compounds):
    apr = num_of_compounds * ((1 + apy) ** Decimal(str((1 / num_of_compounds))) - 1)
    return apr


def get_compound_dai_market():
    token_address = "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643"
    token_calls = []
    token_calls.append(
        (
            token_address,
            [
                "totalSupply()(uint256)",
            ],
            ["total_supply", None],
        )
    )
    token_calls.append(
        (
            token_address,
            [
                "totalBorrows()(uint256)",
            ],
            ["total_borrow", None],
        )
    )
    token_calls.append(
        (
            token_address,
            [
                "exchangeRateStored()(uint256)",
            ],
            ["exchange_rate", None],
        )
    )
    token_calls.append(
        (
            token_address,
            [
                "borrowRatePerBlock()(uint256)",
            ],
            ["borrow_rate", None],
        )
    )
    token_calls.append(
        (
            token_address,
            [
                "supplyRatePerBlock()(uint256)",
            ],
            ["supply_rate", None],
        )
    )

    w3 = Blockchain()
    data = w3.call_multicall(token_calls)
    data["total_supply"] = (data["total_supply"] / 10**8) * (
        data["exchange_rate"] / 10**28
    )
    data["total_borrow"] = data["total_borrow"] / 10**18
    data["supply_rate"] = data["supply_rate"] * BLOCKS_PER_YEAR / 1e18
    data["borrow_rate"] = data["borrow_rate"] * BLOCKS_PER_YEAR / 1e18
    return data


class D3MCompoundCompute:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dai_curve = None
        self._borrow_rate_df_cache = {}
        self._utilization_rate_df_cache = {}
        self._todays_rate = None
        self._defi_rate = None
        self._rates = None
        self._d3m_balance = None

    def get_rates(self):
        if not self._rates:
            rate = get_compound_dai_market()
            self._rates = {
                "total_supply": Decimal(str(rate["total_supply"])),
                "total_borrow": Decimal(str(rate["total_borrow"])),
            }
        return self._rates

    def get_d3m_balance(self):
        if not self._d3m_balance:
            self._d3m_balance = None
        return self._d3m_balance

    @property
    def dai_curve(self):
        if not self._dai_curve:
            kink = Decimal("0.8")
            base = 0
            multiplier_per_block = Decimal("0.000000023782343987")
            jump_multiplier_per_block = Decimal("0.000000518455098934")

            data = []

            utilization_rates = np.around(
                np.linspace(start=0, stop=1, num=10000, endpoint=True), 4
            )

            for utilization in utilization_rates:
                utilization = Decimal(str(utilization))
                if utilization < kink:
                    rate_per_block = base + (utilization * multiplier_per_block)
                    borrow_rate = rate_per_block * BLOCKS_PER_YEAR
                else:
                    normal_rate = base + kink * multiplier_per_block
                    excess_util = utilization - kink
                    rate_per_block = normal_rate + (
                        excess_util * jump_multiplier_per_block
                    )
                    borrow_rate = rate_per_block * BLOCKS_PER_YEAR
                data.append(
                    {
                        "utilization_rate": Decimal(str(utilization)),
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

    def compute_metrics(self, target_borrow_rate, d3m_dc):
        rates = self.get_rates()
        d3m_balance = self.get_d3m_balance() if self.get_d3m_balance() else 0
        d3m_current_dai = max(0, d3m_balance.dai_total) if self.get_d3m_balance() else 0
        d3m_dc_additional = max(0, d3m_dc - d3m_current_dai)
        simulation_dai_borrow = Decimal(int(rates["total_borrow"]))
        d3m_supply_needed = Decimal(
            max(
                int(
                    (
                        simulation_dai_borrow
                        / self.get_utilization_rate_gte(target_borrow_rate)
                    )
                    - rates["total_supply"]
                ),
                0,
            ),
        )
        d3m_exposure = min(d3m_dc_additional, d3m_supply_needed)
        simulation_dai_supply = Decimal(int(rates["total_supply"] + d3m_exposure))
        simulation_utilization_rate = round(
            simulation_dai_borrow / simulation_dai_supply, 6
        )
        simulation_borrow_rate = round(
            self.get_borrow_rate_gte(simulation_utilization_rate),
            6,
        )
        simulation_supply_rate = round(
            simulation_utilization_rate
            * simulation_borrow_rate
            * Decimal(str((1 - RESERVE_FACTOR))),
            6,
        )
        simulation_dai_supply_target = rates["total_supply"] + d3m_supply_needed
        simulation_utilization_rate_target = round(
            rates["total_borrow"] / simulation_dai_supply_target, 6
        )
        implied_supply_rate = round(
            simulation_utilization_rate_target
            * target_borrow_rate
            * Decimal(str((1 - RESERVE_FACTOR))),
            6,
        )

        share_dai_deposits = (d3m_exposure + d3m_current_dai) / simulation_dai_supply
        d3m_revenue_excl_rewards = simulation_supply_rate * (
            d3m_exposure + d3m_current_dai
        )

        return {
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
