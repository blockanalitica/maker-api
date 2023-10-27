# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import contextlib
import math
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import psweep as ps
import pytz
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Avg, F, Sum
from django_bulk_load import bulk_insert_models

from maker.models import OSM, AuctionEvent, AuctionV1, ClipperEvent, Ilk, Vault
from maker.modules.slippage import get_slippage_for_lp, get_slippage_to_dai
from maker.sources.cortex import fetch_cortex_clipper_events
from maker.utils.s3 import download_csv_file_object


def get_auction_dur_stats(cut, buf, percent_liquidated, step, hole, debt):
    if debt == 0:
        debt_exposure_share = 0
    else:
        debt_exposure_share = hole / debt * 100
    auction_cycle = (math.log(1 / buf) / math.log(cut)) * step / 60
    dur_h = math.floor(
        max(
            auction_cycle / 60,
            math.ceil(debt * percent_liquidated / hole) * auction_cycle / 60,
        )
    )
    auction_m = (
        max(
            auction_cycle / 60,
            math.ceil(debt * percent_liquidated / hole) * auction_cycle / 60,
        )
        - dur_h
    ) * 60
    dur_m = math.ceil(auction_m)
    auction_dur = f"{dur_h}h {dur_m}m"
    if auction_cycle == 0:
        auction_dur_m = None
    else:
        auction_dur_m = dur_h * 60 + dur_m
    dur_stats = {
        "debt_exposure_share": debt_exposure_share,
        "auction_cycle": auction_cycle,
        "auction_dur": auction_dur,
        "auction_dur_m": auction_dur_m,
    }

    return dur_stats


def get_stair_step_exponential(buf, cut, step, tail, cusp):
    top = buf * 100
    step /= 60
    tail /= 60
    minutes = list(range(int(tail + 20)))
    stair_step_exponential = []
    for minute in minutes:
        if minute > tail:
            continue
        stair_step = top * pow(cut, math.floor(minute / step))
        if stair_step < top * cusp:
            continue
        stair_step_exponential.append(
            {
                "key": "stairstep_exponential",
                "minute": minute,
                "amount": stair_step,
            }
        )
    return stair_step_exponential


def get_auction_throughput_data_for_ilk(ilk):
    if ilk.type == "lp":
        slippage_to_dai = get_slippage_for_lp(ilk.collateral, ilk.hole)
    else:
        slippage_to_dai = get_slippage_to_dai(ilk.collateral, ilk.hole)
    data = {
        "asset": ilk.collateral,
        "ilk": ilk.ilk,
        "dai": float(ilk.dai_debt or 0),
        "debt_ceiling": float(ilk.debt_ceiling or 0),
        "dc_iam_line": float(ilk.dc_iam_line or 0),
        "lr": float(ilk.lr or 0),
        "chop": float(ilk.chop or 0),
        "current_hole": float(ilk.hole or 0),
        "buf": float(ilk.buf or 0),
        "tail": float(ilk.tail or 0),
        "cusp": float(ilk.cusp or 0),
        "chip": float(ilk.chip or 0),
        "tip": float(ilk.tip or 0),
        "step": float(ilk.step or 0),
        "cut": float(ilk.cut or 0),
        "slippage_to_dai": float(slippage_to_dai or 0),
    }
    return data


class AuctionKickSim:
    cache_timeout = 60 * 60 * 24 * 7  # 1 week

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dates = [
            datetime(2021, 5, 19, 13, 10, tzinfo=pytz.UTC),
            datetime(2021, 5, 23, 16, 43, tzinfo=pytz.UTC),
            datetime(2021, 9, 21, 21, 20, tzinfo=pytz.UTC),
            datetime(2021, 12, 4, 5, 28, tzinfo=pytz.UTC),
            datetime(2022, 1, 21, 23, 11, tzinfo=pytz.UTC),
        ]
        self.dates_map = {d.strftime("%Y-%m-%d"): d for d in self.dates}

    def _fetch_mkt_prices_for_day(self, symbol, day):
        # Fetches low market price per minute
        cache_key = "auctions.minute_prices.{}.{}".format(
            symbol, day.strftime("%Y%m%d")
        )
        cached = cache.get(cache_key)
        if cached:
            return cached

        mkt_prices = {}
        filename = "ohlcv/{}/{}_{}_{}_{}_histominute.csv".format(
            symbol, day.strftime("%Y%m%d"), symbol, "USD", "coinbase"
        )
        reader = download_csv_file_object(filename)
        for row in reader:
            mkt_prices[datetime.fromtimestamp(int(row["time"]), tz=pytz.UTC)] = Decimal(
                row["low"]
            )

        cache.set(cache_key, mkt_prices, timeout=self.cache_timeout)
        return mkt_prices

    def fetch_mkt_prices(self, symbol):
        mkt_prices = {}
        days = deepcopy(self.dates)
        days.append(datetime(2022, 1, 22, tzinfo=pytz.UTC))
        for day in days:
            day_prices = self._fetch_mkt_prices_for_day(symbol, day.date())
            mkt_prices.update(day_prices)

        # Sort them by the key (date)
        return dict(sorted(mkt_prices.items(), key=lambda item: item[0]))

    def market_prices_for_day(self, symbol, date):
        if not date:
            day = self.dates[-1].date()
        else:
            day = self.dates_map[date].date()

        mkt_prices = self.fetch_mkt_prices(symbol)
        prices = []
        for dt, price in mkt_prices.items():
            if dt.date() == day:
                prices.append({"datetime": dt, "price": price})
        return prices

    def _calculate(self, dt, mkt_prices, symbol, cut, step, buf, taker_profit):
        auctions = []
        durations = defaultdict(int)
        num_kicks = 0
        date_from = dt - timedelta(hours=3)
        kick_time = date_from.replace(second=0)
        date_to = dt

        slippages = []

        while kick_time < date_to:
            # For Previous OSM take the mkt price that's 2 hours behind current one
            prev_osm = mkt_prices[kick_time - timedelta(hours=2)]
            osm = mkt_prices[kick_time - timedelta(hours=1)]

            top = osm * buf
            minutes = 0
            # while less then 1 day just to not loop indefinitely in case of some
            # weird data
            # If current OSM is smaller or the same than previous OSM, kick it,
            # otherwise, don't
            if osm <= prev_osm:
                num_kicks += 1

                kick_market_price = mkt_prices[kick_time]
                while minutes < 1440:
                    mkt_price = mkt_prices[(kick_time + timedelta(minutes=minutes))]
                    price = top * pow(cut, math.floor(minutes / (step / 60)))
                    price = price * (1 + taker_profit)
                    if price <= mkt_price:
                        durations[minutes] += 1

                        # They won't pay more than the top, so we limit slippage to that
                        if price > top:
                            slippage = (1 - (top / osm)) * -1
                        else:
                            slippage = (1 - (price / osm)) * -1

                        auctions.append(
                            {
                                "kick_time": kick_time,
                                "kick_market_price": kick_market_price,
                                "current_osm": osm,
                                "top": top,
                                "step_price": price,
                                "duration": minutes,
                                "slippage": slippage,
                            }
                        )
                        slippages.append(slippage)
                        break
                    minutes += 1

            kick_time += timedelta(minutes=1)

        durations = dict(sorted(durations.items(), key=lambda item: item[0]))

        duration_keys = durations.keys()
        pdf = np.array(list(durations.values())) / num_kicks
        cdf = np.cumsum(pdf)

        slippage = {
            "min": min(slippages),
            "max": max(slippages),
            "avg": np.mean(slippages),
            "median": np.median(slippages),
        }
        return {
            "cdf": {
                "durations": list(duration_keys),
                "cdf": list(cdf),
            },
            "slippage": slippage,
            "auctions": auctions,
        }

    def calculate_all_days(self, symbol, cut, step, buf, taker_profit):
        cut = Decimal(str(cut))
        taker_profit = Decimal(str(taker_profit))
        step = Decimal(str(step))
        buf = Decimal(str(buf))

        cache_key = "AuctionKickSim.calculate_all_days.v4.{}.{}.{}.{}.{}".format(
            symbol,
            str(cut).replace(".", "_"),
            str(step).replace(".", "_"),
            str(buf).replace(".", "_"),
            str(taker_profit).replace(".", "_"),
        )
        cached = cache.get(cache_key)
        if cached:
            return cached

        mkt_prices = self.fetch_mkt_prices(symbol)
        data = {}
        for dt in self.dates:
            results = self._calculate(
                dt, mkt_prices, symbol, cut, step, buf, taker_profit
            )

            data[dt.strftime("%Y-%m-%d %H:%M")] = {
                "auctions": results["auctions"],
                "cdf": results["cdf"],
            }
        cache.set(cache_key, data, timeout=self.cache_timeout)
        return data

    def calculate_psets(self, symbol, date, cut, taker_profit):
        assert symbol in ["ETH", "BTC"]

        if not date:
            dt = self.dates[-1]
        else:
            dt = self.dates_map[date]

        cut = Decimal(str(cut))
        taker_profit = Decimal(str(taker_profit))

        cache_key = "AuctionKickSim.calculate_psets.v4.{}.{}.{}.{}".format(
            symbol,
            dt.strftime("%Y-%m-%d"),
            str(cut).replace(".", "_"),
            str(taker_profit).replace(".", "_"),
        )
        cached = cache.get(cache_key)
        if cached:
            return cached

        step_start = 60
        step_end = 170
        step_step = 10
        steps = ps.plist(
            "step", list(range(step_start, step_end + step_step, step_step))
        )

        buf_step = Decimal("0.05")
        buf_start = Decimal("1.05")
        buf_end = Decimal("1.3")
        bufs = ps.plist(
            "buf",
            list(np.arange(buf_start, buf_end + buf_step, buf_step)),
        )

        psets = ps.pgrid([steps, bufs])

        param_data = []

        mkt_prices = self.fetch_mkt_prices(symbol)
        for pset in psets:
            step = int(pset["step"])
            buf = Decimal(str(pset["buf"]))
            results = self._calculate(
                dt, mkt_prices, symbol, cut, step, buf, taker_profit
            )

            percentiles = [
                0.1,
                0.2,
                0.5,
                0.8,
                0.85,
                0.9,
                0.91,
                0.92,
                0.93,
                0.94,
                0.95,
                0.96,
                0.99,
            ]
            cdf = results["cdf"]
            cdf_percentiles = {}
            for percentile in percentiles:
                cdf_value = min(cdf["cdf"], key=lambda x: abs(x - percentile))
                cdf_percentiles[percentile] = cdf["durations"][
                    cdf["cdf"].index(cdf_value)
                ]

            param_data.append(
                {
                    "step": step,
                    "buf": buf,
                    "cdf_percentiles": cdf_percentiles,
                    "slippage": results["slippage"],
                }
            )

        cache.set(cache_key, param_data, timeout=self.cache_timeout)
        return param_data

    def _calculate_osm(
        self, dt, osms, mkt_prices, symbol, cut, step, buf, taker_profit
    ):
        auctions = []
        durations = []
        slippages = []

        for osm in osms:
            top = osm.current_price * buf
            kick_time = datetime.fromtimestamp(osm.timestamp, tz=pytz.UTC).replace(
                second=0
            )
            minutes = 0
            kick_market_price = mkt_prices[kick_time]

            while minutes < 1440:
                mkt_price = mkt_prices[(kick_time + timedelta(minutes=minutes))]
                price = top * pow(cut, math.floor(minutes / (step / 60)))
                price = price * (1 + taker_profit)
                if price <= mkt_price:
                    durations.append(minutes)

                    slippage = (1 - (price / osm.current_price)) * -1

                    auctions.append(
                        {
                            "kick_time": kick_time,
                            "kick_market_price": kick_market_price,
                            "current_osm": osm.current_price,
                            "top": top,
                            "step_price": price,
                            "duration": minutes,
                            "slippage": slippage,
                        }
                    )
                    slippages.append(slippage)
                    break
                minutes += 1

        slippage = {
            "min": min(slippages),
            "max": max(slippages),
            "avg": np.mean(slippages),
            "median": np.median(slippages),
        }
        return {
            "avg_duration": np.mean(durations),
            "slippage": slippage,
            "auctions": auctions,
        }

    def fetch_osm_prices(self, symbol, dt):
        date_from = dt - timedelta(hours=3)
        if symbol == "BTC":
            symbol = "WBTC"
        osms = OSM.objects.filter(
            symbol=symbol,
            timestamp__gte=date_from.timestamp(),
            timestamp__lte=dt.timestamp(),
        )
        return osms

    def fetch_osm_prices_list(self, symbol, date):
        if not date:
            dt = self.dates[-1]
        else:
            dt = self.dates_map[date]

        osms = self.fetch_osm_prices(symbol, dt)
        return [
            {"timestamp": osm.timestamp, "current_price": osm.current_price}
            for osm in osms
        ]

    def calculate_osm_psets(self, symbol, date, cut, taker_profit):
        assert symbol in ["ETH", "BTC"]

        if not date:
            dt = self.dates[-1]
        else:
            dt = self.dates_map[date]

        cut = Decimal(str(cut))
        taker_profit = Decimal(str(taker_profit))

        cache_key = "AuctionKickSim.calculate_osm_psets.v2.{}.{}.{}.{}".format(
            symbol,
            dt.strftime("%Y-%m-%d"),
            str(cut).replace(".", "_"),
            str(taker_profit).replace(".", "_"),
        )
        cached = cache.get(cache_key)
        if cached:
            return cached

        step_start = 60
        step_end = 170
        step_step = 10
        steps = ps.plist(
            "step", list(range(step_start, step_end + step_step, step_step))
        )

        buf_step = Decimal("0.05")
        buf_start = Decimal("1.05")
        buf_end = Decimal("1.3")
        bufs = ps.plist(
            "buf",
            list(np.arange(buf_start, buf_end + buf_step, buf_step)),
        )

        psets = ps.pgrid([steps, bufs])

        param_data = []

        osms = self.fetch_osm_prices(symbol, dt)
        mkt_prices = self.fetch_mkt_prices(symbol)
        for pset in psets:
            step = int(pset["step"])
            buf = Decimal(str(pset["buf"]))
            results = self._calculate_osm(
                dt, osms, mkt_prices, symbol, cut, step, buf, taker_profit
            )

            param_data.append(
                {
                    "step": step,
                    "buf": buf,
                    "avg_duration": results["avg_duration"],
                    "slippage": results["slippage"],
                }
            )

        cache.set(cache_key, param_data, timeout=self.cache_timeout)
        return param_data

    def calculate_all_days_osm(self, symbol, cut, step, buf, taker_profit):
        cut = Decimal(str(cut))
        taker_profit = Decimal(str(taker_profit))
        step = Decimal(str(step))
        buf = Decimal(str(buf))

        cache_key = "AuctionKickSim.calculate_all_days_osm.v2.{}.{}.{}.{}.{}".format(
            symbol,
            str(cut).replace(".", "_"),
            str(step).replace(".", "_"),
            str(buf).replace(".", "_"),
            str(taker_profit).replace(".", "_"),
        )
        cached = cache.get(cache_key)
        if cached:
            return cached

        mkt_prices = self.fetch_mkt_prices(symbol)
        data = {}
        for dt in self.dates:
            osms = self.fetch_osm_prices(symbol, dt)
            results = self._calculate_osm(
                dt, osms, mkt_prices, symbol, cut, step, buf, taker_profit
            )

            data[dt.strftime("%Y-%m-%d %H:%M")] = {
                "auctions": results["auctions"],
            }
        cache.set(cache_key, data, timeout=self.cache_timeout)
        return data


def sync_auctions():
    latest_block = ClipperEvent.latest_block_number()
    save_clipper_events()
    process_clipper_events(latest_block)


def get_auction(ilk, auction_uid):
    auction = AuctionV1.objects.get(ilk=ilk, uid=auction_uid)

    auction_data = {
        "ilk": auction.ilk,
        "uid": auction.uid,
        "auction_start": auction.auction_start,
        "vault": auction.vault,
        "debt": auction.debt,
        "available_collateral": auction.available_collateral,
        "penalty": auction.penalty,
        "sold_collateral": auction.sold_collateral,
        "recovered_debt": auction.recovered_debt,
        "auction_end": auction.auction_end,
        "duration": auction.duration,
        "penalty_fee": auction.penalty_fee,
        "debt_liquidated": auction.debt_liquidated,
        "penalty_fee_per": (auction.penalty_fee or 0) / auction.debt_liquidated,
        "coll_returned": (auction.available_collateral or 0)
        / auction.kicked_collateral,
        "symbol": auction.symbol,
    }
    kicks = AuctionEvent.objects.filter(
        ilk=ilk, auction_uid=auction_uid, type="kick"
    ).values(
        "auction_id",
        "auction_uid",
        "ilk",
        "datetime",
        "debt",
        "available_collateral",
        "sold_collateral",
        "recovered_debt",
        "type",
        "collateral_price",
        "osm_price",
        "mkt_price",
        "keeper",
        "incentives",
        "caller",
    )
    takes = (
        AuctionEvent.objects.filter(ilk=ilk, auction_uid=auction_uid, type="take")
        .annotate(
            osm_settled=(F("collateral_price") / F("osm_price")) - 1,
            mkt_settled=(F("collateral_price") / F("mkt_price")) - 1,
        )
        .values(
            "auction_id",
            "auction_uid",
            "ilk",
            "datetime",
            "debt",
            "available_collateral",
            "sold_collateral",
            "recovered_debt",
            "type",
            "collateral_price",
            "osm_price",
            "mkt_price",
            "keeper",
            "incentives",
            "caller",
            "osm_settled",
            "mkt_settled",
        )
    )
    return list(kicks), list(takes), auction_data


def get_ilk_auctions_per_date(ilk, dt=None):
    return (
        AuctionEvent.objects.filter(
            ilk=ilk, type="take", status=1, auction__auction_start__date=dt
        )
        .annotate(
            osm_settled=(F("collateral_price") / F("osm_price")) - 1,
            mkt_settled=(F("collateral_price") / F("mkt_price")) - 1,
            duration=((F("datetime") - F("auction__auction_start"))),
        )
        .values(
            "auction_uid",
            "ilk",
            "osm_settled",
            "mkt_settled",
            "duration",
            "recovered_debt",
        )
    )


def save_clipper_events():
    latest_block = ClipperEvent.latest_block_number()
    events = fetch_cortex_clipper_events(latest_block)
    bulk_create = []
    for event in events:
        bulk_create.append(ClipperEvent(**event))
        if len(bulk_create) >= 1000:
            bulk_insert_models(bulk_create, ignore_conflicts=True)
            bulk_create = []

    if bulk_create:
        bulk_insert_models(bulk_create, ignore_conflicts=True)


def process_clipper_events(block_number):
    auctions = (
        ClipperEvent.objects.filter(block_number__gt=block_number)
        .order_by("ilk", "auction_id")
        .distinct("ilk", "auction_id")
        .values("ilk", "auction_id")
    )

    for auction in auctions:
        obj, _ = AuctionV1.objects.get_or_create(
            ilk=auction["ilk"], uid=auction["auction_id"]
        )
        kick_event = ClipperEvent.objects.get(
            ilk=auction["ilk"], auction_id=auction["auction_id"], event="Kick"
        )
        try:
            vault = Vault.objects.get(ilk=kick_event.ilk, urn=kick_event.usr.lower())
            obj.symbol = vault.collateral_symbol
            obj.vault = vault.uid
            obj.urn = vault.urn
        except Vault.DoesNotExist:
            ilk_obj = Ilk.objects.get(ilk=kick_event.ilk)
            obj.symbol = ilk_obj.collateral
            obj.vault = None
            obj.urn = kick_event.usr.lower()

        obj.penalty = kick_event.penalty / Decimal("1e18")

        obj.incentive = kick_event.coin / Decimal("1e45")
        obj.auction_start = kick_event.datetime
        obj.kicked_collateral = kick_event.lot / Decimal("1e18")
        obj.available_collateral = kick_event.lot / Decimal("1e18")

        penalty_fee = (kick_event.tab / Decimal("1e45")) - (
            kick_event.tab / Decimal("1e45") / obj.penalty
        )
        start_debt = kick_event.tab / Decimal("1e45")
        obj.debt_liquidated = start_debt - penalty_fee

        take_events = (
            ClipperEvent.objects.filter(
                ilk=auction["ilk"], auction_id=auction["auction_id"], event="Take"
            )
            .annotate(
                osm_settled=(F("price") / Decimal("1e27") / F("osm_price")) - 1,
                mkt_settled=(F("price") / Decimal("1e27") / F("osm_price")) - 1,
            )
            .aggregate(
                recovered_debt=Sum("owe"),
                sold_collateral=Sum(
                    F("owe") / Decimal("1e45") / (F("price") / Decimal("1e27"))
                ),
                avg_osm_price=Avg("osm_settled"),
            )
        )

        obj.sold_collateral = take_events["sold_collateral"]
        obj.available_collateral = max(obj.kicked_collateral - obj.sold_collateral, 0)
        obj.recovered_debt = take_events["recovered_debt"] / Decimal("1e45")
        obj.avg_price = obj.recovered_debt / obj.sold_collateral
        obj.osm_settled_avg = take_events["avg_osm_price"]
        obj.mkt_settled_avg = take_events["avg_osm_price"]

        obj.debt = start_debt - obj.recovered_debt

        obj.penalty_fee = penalty_fee - obj.debt

        obj.finished = (
            obj.debt == max(0, obj.debt)
            or datetime.now() - timedelta(hours=2) > obj.auction_start
        )
        if obj.finished:
            obj.auction_end = (
                ClipperEvent.objects.filter(
                    ilk=auction["ilk"], auction_id=auction["auction_id"], event="Take"
                )
                .latest()
                .datetime
            )
            obj.duration = (obj.auction_end - obj.auction_start).seconds / 60
        obj.save()

        for clipper_event in ClipperEvent.objects.filter(
            ilk=auction["ilk"], auction_id=auction["auction_id"]
        ):
            with contextlib.suppress(IntegrityError):
                AuctionEvent.objects.create(
                    auction=obj,
                    ilk=clipper_event.ilk,
                    auction_uid=clipper_event.auction_id,
                    datetime=clipper_event.datetime,
                    block_number=clipper_event.block_number,
                    tx_hash=clipper_event.tx_hash,
                    order_index=clipper_event.order_index,
                    urn=clipper_event.usr.lower(),
                    debt=clipper_event.owe / Decimal("1e45")
                    if clipper_event.owe
                    else None,
                    available_collateral=clipper_event.lot / Decimal("1e18"),
                    sold_collateral=(clipper_event.owe / Decimal("1e45"))
                    / (clipper_event.price / Decimal("1e27"))
                    if clipper_event.owe
                    else None,
                    recovered_debt=clipper_event.owe / Decimal("1e45")
                    if clipper_event.owe
                    else None,
                    type=clipper_event.event.lower(),
                    collateral_price=clipper_event.price / Decimal("1e27")
                    if clipper_event.price
                    else None,
                    init_price=clipper_event.top / Decimal("1e27")
                    if clipper_event.top
                    else None,
                    osm_price=clipper_event.osm_price if clipper_event.osm_price else 1,
                    mkt_price=clipper_event.osm_price if clipper_event.osm_price else 1,
                    keeper=clipper_event.kpr,
                    incentives=clipper_event.coin / Decimal("1e45")
                    if clipper_event.coin
                    else None,
                )
