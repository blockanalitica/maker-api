# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from functools import wraps

import statsd
from django.conf import settings

statsd_client = statsd.StatsClient(
    settings.STATSD_HOST, settings.STATSD_PORT, settings.STATSD_PREFIX
)
timer = statsd_client.timer


def timerd(key):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not key:
                raise Exception("Using an empty key name")
            with timer(key):
                return func(*args, **kwargs)

        return wrapper

    return decorator


class timer(object):
    def __init__(self, key):
        self.timer = timer(str(key))
        self.key = key

    def __enter__(self):
        self.timer.start()

    def __exit__(self, type_, value, traceback):
        self.timer.stop()


def raw_timer(key, value):
    if not isinstance(value, (int, float)):
        return None

    return statsd_client.timing(str(key), value)


def increment(key, delta=1, subname=None):
    name = "counters.{}".format(key)
    if subname:
        name += ".{}".format(subname)

    return statsd_client.incr(name, delta)


def decrement(key, delta=1, subname=None):
    name = "counters.{}".format(key)
    if subname:
        name += ".{}".format(subname)

    return statsd_client.decr(name, delta)


def gauge(key, value=1, subname=None):
    name = key
    if subname:
        name += ".{}".format(subname)
    if value < 0:
        statsd_client.gauge(name, 0)
    return statsd_client.gauge(name, value)


def function_long_name(func, extra=None):
    if extra:
        return ".".join([func.__module__, func.__name__, extra])
    else:
        return ".".join([func.__module__, func.__name__])


def auto_named_statsd_timer(function_to_decorate):
    call_name = function_long_name(function_to_decorate, "call")

    @wraps(function_to_decorate)
    def incr_and_call(*args, **kwargs):
        statsd_client.incr(call_name)
        return function_to_decorate(*args, **kwargs)

    timer_name = function_long_name(function_to_decorate, "time")
    named_decorator = statsd_client.timer(timer_name)

    return named_decorator(incr_and_call)
