# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from django_bulk_load import bulk_insert_models

from maker.sources.cortex import fetch_cortex_urn_states
from maker.utils.metrics import auto_named_statsd_timer

from ..models import UrnEventState

# ATLAS-API DATA


@auto_named_statsd_timer
def save_urn_event_states():
    latest_block = UrnEventState.latest_block_number()
    urn_states_data = fetch_cortex_urn_states(latest_block)
    bulk_create = []
    for urn_state in urn_states_data:
        bulk_create.append(UrnEventState(**urn_state))
        if len(bulk_create) >= 1000:
            bulk_insert_models(bulk_create, ignore_conflicts=True)
            bulk_create = []

    if bulk_create:
        bulk_insert_models(bulk_create, ignore_conflicts=True)
