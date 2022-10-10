# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0


def simulate(ilk, base_debt, eth_price, liquidation_fees, bark, take, dex_trade):
    # Total gas after events triggered
    if ilk.type == "lp":
        # Includes 2 additional dex trade in gas
        total_gas = (bark + take + 3 * dex_trade) / 1000000000
    else:
        total_gas = (bark + take + dex_trade) / 1000000000

    tip = float(ilk.tip)
    lr = float(ilk.lr)

    gas_gweis = range(0, 5010, 50)

    gas_dais = []
    for gwei in gas_gweis:
        gas = round(eth_price * total_gas * gwei - tip, 2)
        gas_dais.append(gas if gas >= 0 else 0)

    drop_ratios = [(drop, lr * (1 - drop / 100) - 1) for drop in range(0, 75, 5)]
    # Filter out all ratios below 0
    drop_ratios = [x for x in drop_ratios if x[1] >= 0]

    data = []
    for gas_gwei, gas_dai in zip(gas_gweis, gas_dais):
        row = {
            "gas_gwei": gas_gwei,
            "gas_dai": gas_dai,
        }
        for drop, ratio in drop_ratios:
            if base_debt:
                # Required debt to cover TIP costs
                if ratio > liquidation_fees:
                    debt_to_cover = tip / liquidation_fees
                else:
                    debt_to_cover = tip / ratio
                dust = round(gas_dai / ratio + debt_to_cover, 2)
            else:
                dust = round(gas_dai / ratio, 2)

            row[drop] = dust
        data.append(row)
    return data
