# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import math
from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Ilk
from ..modules.auctions import AuctionKickSim

AUCTION_KICK_SIM_ILK_MAP = {"ETH": "ETH-A", "BTC": "WBTC-A"}


class AuctionKickSimPerDayView(APIView):
    def get(self, request, symbol):
        if symbol not in ["ETH", "BTC"]:
            return Response(None, status.HTTP_404_NOT_FOUND)

        ilk_obj = Ilk.objects.get(ilk=AUCTION_KICK_SIM_ILK_MAP[symbol])
        data = {
            "default_settings": {
                "cut": ilk_obj.cut,
                "step": ilk_obj.step,
                "buf": ilk_obj.buf,
            }
        }

        date = request.GET.get("date")
        cut = request.GET.get("cut", ilk_obj.cut)
        taker_profit = request.GET.get("taker_profit", "0.05")

        sim = AuctionKickSim()

        data["param_data"] = sim.calculate_psets(symbol, date, cut, taker_profit)
        data["dates"] = sim.dates
        data["market_prices"] = sim.market_prices_for_day(symbol, date)
        return Response(data, status.HTTP_200_OK)


class AuctionKickSimPerDayOSMView(APIView):
    def get(self, request, symbol):
        if symbol not in ["ETH", "BTC"]:
            return Response(None, status.HTTP_404_NOT_FOUND)

        ilk_obj = Ilk.objects.get(ilk=AUCTION_KICK_SIM_ILK_MAP[symbol])
        data = {
            "default_settings": {
                "cut": ilk_obj.cut,
                "step": ilk_obj.step,
                "buf": ilk_obj.buf,
            }
        }

        date = request.GET.get("date")
        cut = request.GET.get("cut", ilk_obj.cut)
        taker_profit = request.GET.get("taker_profit", "0.05")

        sim = AuctionKickSim()

        data["param_data"] = sim.calculate_osm_psets(symbol, date, cut, taker_profit)
        data["dates"] = sim.dates
        data["market_prices"] = sim.market_prices_for_day(symbol, date)
        data["osms"] = sim.fetch_osm_prices_list(symbol, date)

        return Response(data, status.HTTP_200_OK)


class AuctionKickSimPerParamView(APIView):
    def get(self, request, symbol):
        if symbol not in ["ETH", "BTC"]:
            return Response(None, status.HTTP_404_NOT_FOUND)

        ilk_obj = Ilk.objects.get(ilk=AUCTION_KICK_SIM_ILK_MAP[symbol])
        data = {
            "default_settings": {
                "cut": ilk_obj.cut,
                "step": ilk_obj.step,
                "buf": ilk_obj.buf,
            }
        }

        step = request.GET.get("step", ilk_obj.step)
        buf = request.GET.get("buf", ilk_obj.buf)
        cut = request.GET.get("cut", ilk_obj.cut)
        taker_profit = request.GET.get("taker_profit", "0.05")

        sim = AuctionKickSim()
        data["auctions_by_day"] = sim.calculate_all_days(
            symbol, cut, step, buf, taker_profit
        )
        data["auction_cycle"] = (
            (
                Decimal(str(math.log(1 / Decimal(str(buf)))))
                / Decimal(str(math.log(Decimal(str(cut)))))
            )
            * Decimal(str(step))
            / 60
        )
        data["dates"] = sim.dates

        return Response(data, status.HTTP_200_OK)


class AuctionKickSimPerParamOSMView(APIView):
    def get(self, request, symbol):
        if symbol not in ["ETH", "BTC"]:
            return Response(None, status.HTTP_404_NOT_FOUND)

        ilk_obj = Ilk.objects.get(ilk=AUCTION_KICK_SIM_ILK_MAP[symbol])
        data = {
            "default_settings": {
                "cut": ilk_obj.cut,
                "step": ilk_obj.step,
                "buf": ilk_obj.buf,
            }
        }

        step = request.GET.get("step", ilk_obj.step)
        buf = request.GET.get("buf", ilk_obj.buf)
        cut = request.GET.get("cut", ilk_obj.cut)
        taker_profit = request.GET.get("taker_profit", "0.05")

        sim = AuctionKickSim()
        data["auctions_by_day"] = sim.calculate_all_days_osm(
            symbol, cut, step, buf, taker_profit
        )
        data["auction_cycle"] = (
            (
                Decimal(str(math.log(1 / Decimal(str(buf)))))
                / Decimal(str(math.log(Decimal(str(cut)))))
            )
            * Decimal(str(step))
            / 60
        )
        data["dates"] = sim.dates

        return Response(data, status.HTTP_200_OK)
