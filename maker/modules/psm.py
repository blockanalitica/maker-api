# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

from django.db import connection

from maker.models import Ilk, PSMDAISupply, UrnEventState
from maker.utils.views import fetch_all


def claculate_and_save_psm_dai_supply():
    ilks = Ilk.objects.filter(type="psm", is_active=True).values_list("ilk", flat=True)

    for ilk in ilks:
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        try:
            latest = PSMDAISupply.objects.filter(ilk=ilk).latest()
            from_dt = latest.datetime
            total_supply = Decimal(
                str(
                    UrnEventState.objects.filter(ilk=ilk, datetime__lte=from_dt)
                    .latest()
                    .art
                )
            ) / Decimal("1e18")
        except PSMDAISupply.DoesNotExist:
            total_supply = Decimal("0")
            from_dt = datetime(2000, 1, 1)

        # Don't select events from current hour, as if we do, events that will come
        # later on in the same current hour, won't be counted towards it and will
        # be skipped causing wrong numbers
        sql = """
            SELECT DISTINCT on (dt)
                DATE_TRUNC('hour', datetime) as dt
                , datetime
                , art/1e18 as total_supply
            FROM maker_urneventstate
            WHERE ilk = %s
                AND datetime > %s
                AND datetime < %s
            GROUP BY 1, 2, 3
            ORDER BY 1 DESC, 2 DESC
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, [ilk, from_dt, current_hour])
            events = fetch_all(cursor)

        bulk_create = []
        for event in events:
            supply_change = event["total_supply"] - total_supply
            total_supply = event["total_supply"]
            bulk_create.append(
                PSMDAISupply(
                    ilk=ilk,
                    datetime=event["dt"],
                    timestamp=event["dt"].timestamp(),
                    total_supply=total_supply,
                    supply_change=supply_change,
                )
            )
            if len(bulk_create) == 500:
                PSMDAISupply.objects.bulk_create(bulk_create, ignore_conflicts=True)
                bulk_create = []

        if len(bulk_create) > 0:
            PSMDAISupply.objects.bulk_create(bulk_create, ignore_conflicts=True)
