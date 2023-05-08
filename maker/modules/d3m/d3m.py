# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0


from ...models import D3M, SurplusBuffer
from . import aave, compound


def get_d3m_stats():
    aave_d3m = D3M.objects.filter(protocol="aave").latest()
    comp_d3m = D3M.objects.filter(protocol="compound").latest()
    spark_d3m = D3M.objects.filter(protocol="spark").latest()

    surplus_buffer = SurplusBuffer.objects.latest().amount
    total_balace = aave_d3m.balance + comp_d3m.balance + spark_d3m.balance

    data = {
        "balance": total_balace,
        "debt_ceiling": aave_d3m.max_debt_ceiling
        + comp_d3m.max_debt_ceiling
        + spark_d3m.max_debt_ceiling,
        "surplus_buffer": surplus_buffer,
        "utilization_surplus_buffer": total_balace / surplus_buffer,
    }
    return data


def get_protocol_stats(protocol):
    if protocol == "aave":
        return aave.get_d3m_info()
    if protocol == "compound":
        return compound.get_d3m_info()
