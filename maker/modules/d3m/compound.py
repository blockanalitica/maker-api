# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from django.db.models.functions import TruncHour
from eth_utils import to_checksum_address

from maker.models import D3M, SurplusBuffer
from maker.sources.blockanalitica import fetch_compound_historic_rate
from maker.utils.blockchain.chain import Blockchain

from .helper import get_d3m_contract_data

D3M_COMP = "0x621fE4Fde2617ea8FFadE08D0FF5A862aD287EC2"
COMPTROLLER_ADDRESS = "0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3B"


RESERVE_FACTOR = 0.15
BLOCKS_PER_YEAR = 2628000
ILK = "DIRECT-COMPV2-DAI"


def get_current_balance(balance_contract):
    chain = Blockchain()
    contract = chain.get_contract(
        "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643", abi_type="ceth"
    )
    data = contract.caller.balanceOf(to_checksum_address(balance_contract))
    exchange_rate = contract.caller.exchangeRateStored()
    return round(
        (Decimal(data) / Decimal(1e8)) * (Decimal(exchange_rate) / Decimal(1e28)), 2
    )


def save_d3m():
    ilk = "DIRECT-COMPV2-DAI"
    data = get_d3m_contract_data(ilk)
    dt = datetime.now()
    balance = get_current_balance(data["balance_contract"])
    D3M.objects.create(
        timestamp=dt.timestamp(),
        datetime=dt,
        protocol="compound",
        balance=balance,
        ilk=ilk,
        **data,
    )


def get_d3m_short_info():
    d3m_data = D3M.objects.filter(protocol="compound").latest()
    balance = get_current_balance(d3m_data.balance_contract)
    return {
        "protocol": "Compound",
        "protocol_slug": "compound",
        "balance": balance,
        "max_debt_ceiling": d3m_data.max_debt_ceiling,
        "target_borrow_rate": d3m_data.target_borrow_rate,
        "symbol": "DAI",
        "title": "Compound",
        "utilization": balance / d3m_data.max_debt_ceiling,
        "pending": False,
    }


def get_d3m_info():
    ilk = "DIRECT-COMPV2-DAI"
    d3m_data = D3M.objects.filter(ilk=ilk).latest()
    surplus_buffer = SurplusBuffer.objects.latest().amount
    stats = get_compound_dai_market()
    balance = get_current_balance(d3m_data.balance_contract)
    data = {
        "protocol": "Compound",
        "protocol_slug": "compound",
        "balance": balance,
        "debt_ceiling": d3m_data.max_debt_ceiling,
        "target_borrow_rate": d3m_data.target_borrow_rate,
        "symbol": "DAI",
        "title": "Compound",
        "utilization_balance": balance / d3m_data.max_debt_ceiling,
        "surplus_buffer": surplus_buffer,
        "utilization_surplus_buffer": balance / surplus_buffer,
        "supply_utilization": stats["total_borrow"] / stats["total_supply"],
    }

    data.update(stats)
    return data


def get_historic_rates(days_ago=30):
    ilk = ILK
    dt = datetime.now() - timedelta(days=days_ago)
    target_borrow_rates = (
        D3M.objects.filter(ilk=ilk, datetime__gte=dt)
        .annotate(dt=TruncHour("datetime"))
        .values("target_borrow_rate", "dt")
    )
    historic_rates = fetch_compound_historic_rate("DAI", days_ago)

    return {
        "borrow_rates": historic_rates,
        "target_borrow_rates": target_borrow_rates,
    }


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

    token_calls.append(
        (
            COMPTROLLER_ADDRESS,
            ["compSupplySpeeds(address)(uint256)", token_address],
            ["supply_rewards_rate", None],
        )
    )
    token_calls.append(
        (
            "0x65c816077C29b557BEE980ae3cC2dCE80204A0C5",
            ["price(string)(uint256)", "COMP"],
            ["comp_price", None],
        )
    )
    token_calls.append(
        (
            "0x65c816077C29b557BEE980ae3cC2dCE80204A0C5",
            ["getUnderlyingPrice(address)(uint256)", token_address],
            ["underlying_price", None],
        )
    )

    w3 = Blockchain()
    data = w3.call_multicall(token_calls)
    underlying_price = Decimal(data["underlying_price"]) / Decimal(1e18)
    data["total_supply"] = (data["total_supply"] / 10**8) * (
        data["exchange_rate"] / 10**28
    )
    data["total_borrow"] = data["total_borrow"] / 10**18
    data["supply_rate"] = data["supply_rate"] * BLOCKS_PER_YEAR / 1e18
    data["borrow_rate"] = data["borrow_rate"] * BLOCKS_PER_YEAR / 1e18
    data["exchange_rate"] = data["exchange_rate"]
    data["utilization"] = data["total_borrow"] / data["total_supply"]
    supply_reward_rate = 0
    supply_reward_emission = data["supply_rewards_rate"] / 1e18
    if supply_reward_emission > 0:
        comp_supply_rewards_per_year = Decimal(supply_reward_emission * BLOCKS_PER_YEAR)
        supply_reward_rate = (
            Decimal((Decimal(data["comp_price"]) / Decimal(1e6)))
            * Decimal(comp_supply_rewards_per_year)
        ) / (Decimal(data["total_supply"]) * underlying_price)
    data["supply_reward_rate"] = supply_reward_rate
    data["comp_price"] = Decimal(data["comp_price"]) / Decimal(1e6)
    data["comp_supply_rewards_per_year"] = comp_supply_rewards_per_year
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
        self._d3m_model = None

    def get_rates(self):
        if not self._rates:
            rate = get_compound_dai_market()
            self._rates = {
                "total_supply": Decimal(str(rate["total_supply"])),
                "total_borrow": Decimal(str(rate["total_borrow"])),
                "borrow_rate": Decimal(str(rate["borrow_rate"])),
                "supply_rate": Decimal(str(rate["supply_rate"])),
                "supply_rate_reward": Decimal(str(rate["supply_rate"])),
                "comp_price": Decimal(str(rate["comp_price"])),
                "comp_supply_rewards_per_year": Decimal(
                    str(rate["comp_supply_rewards_per_year"])
                ),
            }
        return self._rates

    @property
    def d3m_model(self):
        if not self._d3m_model:
            self._d3m_model = D3M.objects.filter(protocol="compound").latest()
        return self._d3m_model

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
        # d3m_balance = self.get_d3m_balance() if self.get_d3m_balance() else 0
        # d3m_current_dai = max(0, d3m_balance.dai_total) if self.get_d3m_balance() else 0
        d3m_dc_additional = max(0, d3m_dc - d3m_current_dai)
        simulation_dai_borrow = Decimal(int(dai_borrow))
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
            * simulation_borrow_rate
            * Decimal(str((1 - RESERVE_FACTOR))),
            6,
        )
        simulation_dai_supply_target = dai_supply + d3m_supply_needed
        simulation_utilization_rate_target = round(
            dai_borrow / simulation_dai_supply_target, 6
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

        simulation_supply_reward_rate = (
            Decimal((rates["comp_price"]))
            * Decimal(rates["comp_supply_rewards_per_year"])
        ) / (Decimal(simulation_dai_supply))

        d3m_revenue_rewards = simulation_supply_reward_rate * (
            d3m_exposure + d3m_current_dai
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
            "simulation_supply_reward_rate": simulation_supply_reward_rate,
            "share_dai_deposits": share_dai_deposits,
            "d3m_revenue": d3m_revenue_excl_rewards,
            "d3m_revenue_rewards": d3m_revenue_rewards,
            "d3m_balance": d3m_current_dai,
            "d3m_exposure_total": d3m_current_dai + d3m_exposure,
        }

        if unwind:
            data["d3m_exposure_total"] = d3m_exposure
            data["d3m_balance"] = old_current_dai
            data["d3m_exposure"] = d3m_exposure - old_current_dai
        return data
