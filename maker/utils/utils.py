# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import date, datetime, timedelta
from decimal import Decimal


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def date_to_timestamp(dt):
    from_datetime = datetime(year=dt.year, month=dt.month, day=dt.day)
    return int(datetime.timestamp(from_datetime))


def get_today_timestamp():
    today = date.today()
    return date_to_timestamp(today)


def get_yesterday_timestamp():
    yesterday = date.today() - timedelta(days=1)
    return date_to_timestamp(yesterday)


def yesterday_date():
    return date.today() - timedelta(days=1)


def get_date_days_ago(number_of_days, start_date=None):
    if not start_date:
        start_date = date.today()
    dt = start_date - timedelta(days=number_of_days)
    return date(year=dt.year, month=dt.month, day=dt.day)


def get_date_timestamp_days_ago(number_of_days, start_date=None):
    dt = get_date_days_ago(number_of_days=number_of_days, start_date=start_date)
    return date_to_timestamp(dt)


def get_date_timestamp_eod(dt):
    """Returns timestamp at the end of day (23:59:59)"""
    return datetime(dt.year, dt.month, dt.day, 23, 59, 59).timestamp()


def timestamp_to_full_hour(dt):
    dt = dt.replace(second=0, microsecond=0, minute=0, hour=dt.hour)
    return int(datetime.timestamp(dt))


def format_num(num):
    if num >= 1000000000:
        value = "{:.0f}{}".format(num / Decimal("1000000000"), "B")
    elif num >= 1000000:
        value = "{:.0f}{}".format(num / Decimal("1000000"), "M")
    elif num >= 1000:
        value = "{:.0f}{}".format(num / Decimal("1000"), "k")
    else:
        value = str(num)
    return value


def calculate_rate(
    old_liquidity_index, old_timestamp, new_liquidity_index, new_timestamp
):
    if old_timestamp == new_timestamp:
        return Decimal("0")
    return (
        (Decimal(new_liquidity_index) / Decimal(old_liquidity_index) - Decimal(1))
        / Decimal(new_timestamp - old_timestamp)
        * Decimal(new_timestamp - old_timestamp)
    )


def round_to_closest(number, base=5):
    return base * round(number / base)
