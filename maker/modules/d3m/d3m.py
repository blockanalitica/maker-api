# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from ...models import D3M, SurplusBuffer
from . import aave, compound


def get_d3m_stats():
    d3m = D3M.objects.latest()

    surplus_buffer = SurplusBuffer.objects.latest().amount
    total_balace = d3m.balance

    data = {
        "balance": total_balace,
        "debt_ceiling": d3m.max_debt_ceiling,
        "surplus_buffer": surplus_buffer,
        "utilization": total_balace / surplus_buffer,
    }
    return data


def get_protocol_stats(protocol):
    if protocol == "aave":
        return aave.get_d3m_info()
    if protocol == "compound":
        return compound.get_d3m_info()
