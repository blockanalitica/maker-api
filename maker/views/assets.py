# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from django.db.models import F, Sum, Value
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from maker.constants import (
    DRAWDOWN_PAIRS_HISTORY_DAYS,
    OHLCV_TYPE_DAILY,
    OHLCV_TYPE_HOURLY,
    OHLCV_TYPES,
)
from maker.models import (
    OHLCV,
    OSM,
    Asset,
    LiquidityScore,
    MakerAsset,
    MakerAssetCollateral,
    MakerAssetDebt,
    MarketPrice,
    Medianizer,
    OHLCVPair,
    OSMDaily,
    PoolInfo,
    SlippageDaily,
    Vault,
    Volatility,
)
from maker.modules.slippage import get_slippage_from_asset, get_slippage_history
from maker.utils.utils import date_to_timestamp, round_to_closest


class AssetPricesView(APIView):
    def get(self, request, symbol):
        # Since this is a Maker endpoint, check that the maker asset exists even
        # though we don't use it later on
        get_object_or_404(MakerAsset, symbol=symbol)

        underlying_symbol = symbol
        if symbol == "WSTETH":
            underlying_symbol = "STETH"

        asset = get_object_or_404(Asset, underlying_symbol__iexact=underlying_symbol)

        data = {}

        days_ago = int(request.GET.get("days_ago"))
        mkt_price = asset.price

        try:
            medianizer_price = Medianizer.objects.filter(symbol=symbol).latest().price
        except Medianizer.DoesNotExist:
            medianizer_price = None
        try:
            osm = OSM.objects.filter(symbol=symbol).latest()
            data["osm_current_price"] = osm.current_price
            data["osm_next_price"] = osm.next_price
        except OSM.DoesNotExist:
            osm = None

        mkt_price_diff = None
        if days_ago:
            timestamp = (datetime.now() - timedelta(days=int(days_ago))).timestamp()

            try:
                mkt_before_price = (
                    MarketPrice.objects.filter(
                        symbol=asset.symbol, timestamp__lte=timestamp
                    )
                    .latest()
                    .price
                )
            except MarketPrice.DoesNotExist:
                pass
            else:
                mkt_price_diff = (mkt_price - mkt_before_price) / mkt_before_price * 100

            if medianizer_price:
                medianizer_before_price = (
                    Medianizer.objects.filter(symbol=symbol, timestamp__lte=timestamp)
                    .latest()
                    .price
                )
                medianizer_price_diff = (
                    (medianizer_price - medianizer_before_price)
                    / medianizer_before_price
                    * 100
                )
                data["medianizer_price_diff"] = medianizer_price_diff
            if osm:
                osm_before = OSM.objects.filter(
                    symbol=symbol, timestamp__lte=timestamp
                ).latest()

                osm_price_diff = (
                    (osm.current_price - osm_before.current_price)
                    / osm_before.current_price
                    * 100
                )
                data["osm_price_diff"] = osm_price_diff

        data["mkt_price"] = mkt_price
        data["mkt_price_diff"] = mkt_price_diff
        data["medianizer_price"] = medianizer_price
        return Response(data, status.HTTP_200_OK)


class AssetLiquidityScoreView(APIView):
    def get(self, request, symbol):
        if symbol == "ETH":
            symbol = "WETH"
        try:
            score = LiquidityScore.objects.filter(symbol=symbol).latest()
        except LiquidityScore.DoesNotExist:
            return Response(None, status.HTTP_404_NOT_FOUND)

        data = [{"date": k, "score": v} for k, v in score.over_time.items()]
        return Response(data, status.HTTP_200_OK)


class AssetsView(APIView):
    def get(self, request):
        asset_symbols = list(
            MakerAsset.objects.filter(is_active=True, type="asset")
            .values_list("symbol", flat=True)
            .order_by("symbol")
        )
        vault_data = (
            Vault.objects.filter(collateral_symbol__in=asset_symbols)
            .values("collateral_symbol")
            .annotate(debt=Sum("debt"), collateral=Sum("collateral"))
        )
        additional_data = {}
        for vd in vault_data:
            additional_data[vd["collateral_symbol"]] = vd

        data = []
        for symbol in asset_symbols:
            additional = additional_data.get(symbol)
            asset_info = {
                "symbol": symbol,
                "debt": 0,
                "collateral": 0,
            }
            if additional:
                asset_info["debt"] = additional["debt"]
                asset_info["collateral"] = additional["collateral"]
            data.append(asset_info)
        return Response(data, status.HTTP_200_OK)


class AssetSlippageView(APIView):
    def get(self, request, symbol):
        get_object_or_404(MakerAsset, symbol=symbol)
        if symbol == "WSTETH":
            symbol = "wstETH"
        asset = get_object_or_404(Asset, underlying_symbol__iexact=symbol)
        data = []
        for symbol, values in get_slippage_from_asset(asset, source="cow").items():
            for key, value in values.items():
                item = {
                    "symbol": symbol,
                    "amount": key,
                    "slippage": value,
                }
                data.append(item)
        return Response(data, status.HTTP_200_OK)


class AssetSlippageHistoryView(APIView):
    def get(self, request, symbol):
        get_object_or_404(MakerAsset, symbol=symbol)
        if symbol == "WSTETH":
            symbol = "wstETH"
        asset = get_object_or_404(Asset, underlying_symbol__iexact=symbol)
        data = []
        for symbol, values in get_slippage_history(asset).items():
            for key, value in values.items():
                item = {
                    "symbol": symbol,
                    "amount": key,
                    "slippage": value,
                }
                data.append(item)

        return Response(data, status.HTTP_200_OK)


class AssetCEXTradingActivityView(APIView):
    def get(self, request, symbol):
        get_object_or_404(MakerAsset, symbol=symbol)
        if symbol in {"WBTC", "WSTETH"}:
            symbol = symbol.lstrip("W")

        data = (
            OHLCV.objects.filter(
                pair__from_asset_symbol=symbol,
                pair__is_active=True,
                pair__ohlcv_type="histoday",
                datetime__gte=datetime.now() - timedelta(days=90),
            )
            .order_by("timestamp")
            .values("timestamp")
            .annotate(key=Value(symbol), amount=Sum("volume_usd"))
        )
        return Response(data, status.HTTP_200_OK)


class AssetCEXTradingActivityPerExchangeView(APIView):
    def get(self, request, symbol):
        get_object_or_404(MakerAsset, symbol=symbol)
        if symbol in {"WBTC", "WSTETH"}:
            symbol = symbol.lstrip("W")
        ohlcvs = (
            OHLCV.objects.filter(
                pair__from_asset_symbol=symbol,
                pair__is_active=True,
                ohlcv_type="histoday",
                datetime__gte=datetime.now() - timedelta(days=90),
            )
            .values("timestamp", exchange=F("pair__exchange"))
            .annotate(amount=Sum("volume_usd"))
            .order_by("exchange", "timestamp")
        )
        return Response(ohlcvs, status.HTTP_200_OK)


class AssetCEXTradingActivityPerAssetView(APIView):
    def get(self, request, symbol):
        get_object_or_404(MakerAsset, symbol=symbol)
        if symbol in {"WBTC", "WSTETH"}:
            symbol = symbol.lstrip("W")
        ohlcvs = (
            OHLCV.objects.filter(
                pair__from_asset_symbol=symbol,
                pair__is_active=True,
                ohlcv_type="histoday",
                datetime__gte=datetime.now() - timedelta(days=90),
            )
            .values("timestamp", asset=F("pair__to_asset_symbol"))
            .annotate(amount=Sum("volume_usd"))
            .order_by("asset", "timestamp")
        )
        return Response(ohlcvs, status.HTTP_200_OK)


class AssetDEXTradingActivityVolumeView(APIView):
    def get(self, request, symbol):
        asset = get_object_or_404(MakerAsset, symbol=symbol)
        if asset.symbol in {"ETH", "BTC"}:
            symbol = "W{}".format(asset.symbol)
        if asset.symbol == "WSTETH":
            symbol = "STETH"

        data = (
            PoolInfo.objects.filter(
                pool__from_asset_symbol=symbol,
                datetime__gte=datetime.now() - timedelta(days=90),
            )
            .values("timestamp", exchange=F("pool__exchange"))
            .annotate(amount=Sum("volume_usd"))
            .order_by("exchange", "timestamp")
        )
        return Response(data, status.HTTP_200_OK)


class AssetDEXTradingActivityLiquidityView(APIView):
    def get(self, request, symbol):
        asset = get_object_or_404(MakerAsset, symbol=symbol)
        if asset.symbol in {"ETH", "BTC"}:
            symbol = "W{}".format(asset.symbol)
        if asset.symbol == "WSTETH":
            symbol = "STETH"

        data = (
            PoolInfo.objects.filter(
                pool__from_asset_symbol=symbol,
                datetime__gte=datetime.now() - timedelta(days=90),
            )
            .values("timestamp", exchange=F("pool__exchange"))
            .annotate(amount=Sum("reserve_usd"))
            .order_by("exchange", "timestamp")
        )
        return Response(data, status.HTTP_200_OK)


class AssetDailyVolatilityView(APIView):
    def _get_pair(self, symbol):
        if symbol in {"WBTC", "WSTETH"}:
            symbol = symbol.lstrip("W")
        keys = DRAWDOWN_PAIRS_HISTORY_DAYS.keys()
        for key in keys:
            from_symbol, to_symbol, exchange, ohlcv_type = key.split("-")
            if from_symbol != symbol or ohlcv_type != OHLCV_TYPE_HOURLY:
                continue
            return OHLCVPair.objects.get(
                from_asset_symbol=from_symbol,
                to_asset_symbol=to_symbol,
                ohlcv_type=ohlcv_type,
                exchange=exchange,
            )

    def get(self, request, symbol):
        asset = get_object_or_404(MakerAsset, symbol=symbol)
        pair = self._get_pair(asset.symbol)
        if not pair:
            raise Http404()

        data = (
            Volatility.objects.filter(pair=pair)
            .values("date", "volatility")
            .order_by("date")
        )
        return Response(data, status.HTTP_200_OK)


class AssetPriceDrawdownsView(APIView):
    def _get_drawdawn_pair_ids_for_asset(self, symbol):
        keys = DRAWDOWN_PAIRS_HISTORY_DAYS.keys()
        pairs = defaultdict(list)
        for key in keys:
            from_symbol, to_symbol, exchange, ohlcv_type = key.split("-")
            if from_symbol != symbol:
                continue

            pair_ids = OHLCVPair.objects.filter(
                from_asset_symbol=from_symbol,
                to_asset_symbol=to_symbol,
                ohlcv_type=ohlcv_type,
                exchange=exchange,
            ).values_list("id", flat=True)
            pairs[ohlcv_type] += pair_ids
        return pairs

    def get(self, request, symbol):
        asset = get_object_or_404(MakerAsset, symbol=symbol)

        if asset.symbol in {"WBTC", "WSTETH"}:
            symbol = symbol.lstrip("W")

        ohlcv_pairs = self._get_drawdawn_pair_ids_for_asset(symbol)

        results = []
        timestamps = {}
        for ohlcv_type, pair_ids in ohlcv_pairs.items():
            key_type = dict(OHLCV_TYPES)[ohlcv_type]
            ohlcvs = OHLCV.objects.filter(
                pair_id__in=pair_ids,
                drawdown__lt=-2,
                drawdown_hl__isnull=False,
            ).order_by("timestamp")

            drawdown_hls = ohlcvs.values_list("drawdown_hl", flat=True)

            start_timestamp = ohlcvs.first().timestamp
            end_timestamp = ohlcvs.last().timestamp

            counter = defaultdict(int)
            for drawdown_hl in drawdown_hls:
                bucket = round_to_closest(drawdown_hl)
                if bucket < 0 and bucket > -80:
                    counter[bucket] += 1

            timestamps[key_type] = {
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
            }

            key = "{} {}".format(symbol, key_type)
            for drop, count in counter.items():
                results.append(
                    {
                        "key": key,
                        "drop": drop,
                        "amount": count,
                    }
                )

        if asset.symbol != "ETH" and timestamps:
            eth_pairs = self._get_drawdawn_pair_ids_for_asset("ETH")

            for ohlcv_type, pair_ids in eth_pairs.items():
                key_type = dict(OHLCV_TYPES)[ohlcv_type]

                ohlcvs = OHLCV.objects.filter(
                    pair_id__in=pair_ids,
                    drawdown__lt=-2,
                    drawdown_hl__isnull=False,
                    timestamp__gte=timestamps[key_type]["start_timestamp"],
                ).order_by("timestamp")

                drawdown_hls = ohlcvs.values_list("drawdown_hl", flat=True)

                counter = defaultdict(int)
                for drawdown_hl in drawdown_hls:
                    bucket = round_to_closest(drawdown_hl)
                    if bucket < 0 and bucket > -80:
                        counter[bucket] += 1

                key = "ETH {}".format(key_type)
                for drop, count in counter.items():
                    results.append(
                        {
                            "key": key,
                            "drop": drop,
                            "amount": count,
                        }
                    )

        data = [results, timestamps]
        return Response(data, status.HTTP_200_OK)


class AssetOSMDrawdownsCountView(APIView):
    def _get_OSM_hourly_count(self, asset):
        osms = (
            OSM.objects.filter(symbol=asset.symbol, current_price__gt=0)
            .values("current_price", "next_price", "datetime")
            .order_by("datetime")
        )
        osms = list(osms)

        if len(osms) < 2:
            return None, None, None

        start_timestamp = osms[0]["datetime"].timestamp()
        end_timestamp = osms[-1]["datetime"].timestamp()
        drawdowns = []
        for osm in osms:
            drawdown = (
                (osm["next_price"] - osm["current_price"]) / osm["current_price"] * 100
            )
            if drawdown <= -2:
                bucket = round_to_closest(drawdown)
                if bucket < 0:
                    drawdowns.append(bucket)
        return start_timestamp, end_timestamp, Counter(drawdowns)

    def _get_OSM_daily_count(self, asset):
        osms = list(OSMDaily.objects.filter(symbol=asset.symbol).order_by("date"))
        if len(osms) < 2:
            return None, None, None
        start_timestamp = osms[0].timestamp
        end_timestamp = osms[-1].timestamp
        drawdowns = []
        for osm in osms:
            drop = round_to_closest(osm.greatest_drop)
            if drop < 0:
                drawdowns.append(drop)
        return start_timestamp, end_timestamp, Counter(drawdowns)

    def get(self, request, symbol):
        asset = get_object_or_404(MakerAsset, symbol=symbol)
        timestamps = {}
        drawdown_data = []
        (
            daily_start_timestamp,
            daily_end_timestamp,
            daily_counter,
        ) = self._get_OSM_daily_count(asset)
        if not daily_counter:
            return None, None
        daily_key = f"{asset.symbol} daily"
        for drop, count in daily_counter.items():
            drawdown_data.append(
                {
                    "key": daily_key,
                    "drop": drop,
                    "amount": count,
                }
            )
        timestamps["daily"] = {
            "start_timestamp": daily_start_timestamp,
            "end_timestamp": daily_end_timestamp,
        }
        (
            hourly_start_timestamp,
            hourly_end_timestamp,
            hourly_counter,
        ) = self._get_OSM_hourly_count(asset)
        hourly_key = f"{asset.symbol} hourly"
        for drop, count in hourly_counter.items():
            drawdown_data.append(
                {
                    "key": hourly_key,
                    "drop": drop,
                    "amount": count,
                }
            )
        timestamps["hourly"] = {
            "start_timestamp": hourly_start_timestamp,
            "end_timestamp": hourly_end_timestamp,
        }
        data = [drawdown_data, timestamps]
        return Response(data, status.HTTP_200_OK)


class AssetsSlippagesView(APIView):
    def get(self, request):
        symbols = list(
            MakerAsset.objects.filter(type="asset", is_active=True)
            .values_list("symbol", flat=True)
            .order_by("symbol")
        )

        symbols.remove("WSTETH")
        symbols.append("wstETH")

        latest = SlippageDaily.objects.latest()
        slippages = (
            SlippageDaily.objects.filter(
                date=latest.date,
                pair__from_asset__underlying_symbol__in=symbols,
                slippage_percent__isnull=False,
            )
            .select_related("pair", "from_asset", "to_asset")
            .values(
                "usd_amount",
                "pair__from_asset__symbol",
                "pair__to_asset__symbol",
                "slippage_percent",
            )
            .order_by("usd_amount")
        )

        data = []
        for slippage in slippages:
            if not slippage["slippage_percent"]:
                continue

            fa = slippage["pair__from_asset__symbol"]
            ta = slippage["pair__to_asset__symbol"]
            data.append(
                {
                    "key": f"{fa}-{ta}",
                    "usd_amount": slippage["usd_amount"],
                    "amount": round(slippage["slippage_percent"], 2),
                }
            )
        return Response(data, status.HTTP_200_OK)


class AssetsCEXVolumeView(APIView):
    def get(self, request):
        data = []
        for asset in MakerAsset.objects.filter(type="asset", is_active=True).order_by(
            "symbol"
        ):
            symbol = asset.symbol
            if symbol in {"WBTC", "WSTETH"}:
                symbol = symbol.lstrip("W")

            ohlcv_data = (
                OHLCV.objects.filter(
                    pair__from_asset_symbol=symbol,
                    pair__is_active=True,
                    pair__ohlcv_type="histoday",
                    datetime__gte=datetime.now() - timedelta(days=90),
                )
                .order_by("timestamp")
                .values("timestamp")
                .annotate(key=Value(symbol), amount=Sum("volume_usd"))
            )
            data.extend(ohlcv_data)

        return Response(data, status.HTTP_200_OK)


class AssetsDEXVolumeView(APIView):
    def get(self, request):
        data = []
        for asset in MakerAsset.objects.filter(type="asset", is_active=True).order_by(
            "symbol"
        ):
            symbol = asset.symbol
            if symbol in {"ETH", "BTC"}:
                symbol = "W{}".format(asset.symbol)
            if symbol == "WSTETH":
                symbol = "STETH"

            pool_data = (
                PoolInfo.objects.filter(
                    pool__from_asset_symbol=symbol,
                    datetime__gte=datetime.now() - timedelta(days=90),
                )
                .values("timestamp", key=F("pool__from_asset_symbol"))
                .annotate(amount=Sum("volume_usd"))
                .order_by("key", "timestamp")
            )
            data.extend(pool_data)

        return Response(data, status.HTTP_200_OK)


class AssetsDEXLiquidityView(APIView):
    def get(self, request):
        data = []
        for asset in MakerAsset.objects.filter(type="asset", is_active=True).order_by(
            "symbol"
        ):
            symbol = asset.symbol
            if symbol in {"ETH", "BTC"}:
                symbol = "W{}".format(asset.symbol)
            if symbol == "WSTETH":
                symbol = "STETH"

            pool_data = (
                PoolInfo.objects.filter(
                    pool__from_asset_symbol=symbol,
                    datetime__gte=datetime.now() - timedelta(days=90),
                )
                .values("timestamp", key=F("pool__from_asset_symbol"))
                .annotate(amount=Sum("reserve_usd"))
                .order_by("key", "timestamp")
            )
            data.extend(pool_data)

        return Response(data, status.HTTP_200_OK)


class AssetsVolatilityView(APIView):
    def _get_pairs(self):
        asset_symbols = (
            MakerAsset.objects.filter(type="asset", is_active=True)
            .values_list("symbol", flat=True)
            .order_by("symbol")
        )
        symbols = []
        for symbol in asset_symbols:
            if symbol in {"WBTC", "WSTETH"}:
                symbol = symbol.lstrip("W")
            symbols.append(symbol)

        pairs = []
        keys = DRAWDOWN_PAIRS_HISTORY_DAYS.keys()
        for key in keys:
            from_symbol, to_symbol, exchange, ohlcv_type = key.split("-")
            if from_symbol not in symbols or ohlcv_type != OHLCV_TYPE_HOURLY:
                continue
            pair = OHLCVPair.objects.get(
                from_asset_symbol=from_symbol,
                to_asset_symbol=to_symbol,
                ohlcv_type=ohlcv_type,
                exchange=exchange,
            )
            pairs.append(pair)
        return pairs

    def get(self, request):
        data = []
        pairs = self._get_pairs()

        volatility = (
            Volatility.objects.filter(
                date__gte=date.today() - timedelta(days=90), pair__in=pairs
            )
            .order_by("date")
            .select_related("pair")
        )
        for item in volatility:
            data.append(
                {
                    "key": item.pair.from_asset_symbol,
                    "timestamp": date_to_timestamp(item.date),
                    "amount": item.volatility,
                }
            )

        return Response(data, status.HTTP_200_OK)


class AssetsDrawdownsView(APIView):
    def _get_drawdawn_pair_ids_for_asset(self, symbol):
        keys = DRAWDOWN_PAIRS_HISTORY_DAYS.keys()
        pairs = defaultdict(list)
        for key in keys:
            from_symbol, to_symbol, exchange, ohlcv_type = key.split("-")
            if from_symbol != symbol or ohlcv_type != OHLCV_TYPE_DAILY:
                continue

            pair_ids = OHLCVPair.objects.filter(
                from_asset_symbol=from_symbol,
                to_asset_symbol=to_symbol,
                ohlcv_type=ohlcv_type,
                exchange=exchange,
            ).values_list("id", flat=True)
            pairs[ohlcv_type] += pair_ids
        return pairs

    def get(self, request):
        data = []

        symbols = (
            MakerAsset.objects.filter(type="asset", is_active=True)
            .values_list("symbol", flat=True)
            .order_by("symbol")
        )

        for symbol in symbols:
            if symbol in {"WBTC", "WSTETH"}:
                symbol = symbol.lstrip("W")

            ohlcv_pairs = self._get_drawdawn_pair_ids_for_asset(symbol)

            for ohlcv_type, pair_ids in ohlcv_pairs.items():
                ohlcvs = OHLCV.objects.filter(
                    pair_id__in=pair_ids,
                    drawdown__lt=-2,
                    drawdown_hl__isnull=False,
                ).order_by("timestamp")

                drawdown_hls = ohlcvs.values_list("drawdown_hl", flat=True)

                counter = defaultdict(int)
                for drawdown_hl in drawdown_hls:
                    bucket = round_to_closest(drawdown_hl)
                    if bucket < 0 and bucket > -80:
                        counter[bucket] += 1

                for drop, count in counter.items():
                    data.append(
                        {
                            "key": symbol,
                            "drop": drop,
                            "amount": count,
                        }
                    )

        return Response(data, status.HTTP_200_OK)


class AssetCollateralView(APIView):
    def get(self, request, token_address):
        try:
            asset = MakerAssetCollateral.objects.filter(
                token_address__iexact=token_address
            ).latest()
        except MakerAssetCollateral.DoesNotExist:
            raise Http404()

        data = []
        for item in asset.positions.all():
            data.append(
                {
                    "symbol": item.underlying_symbol,
                    "amount": item.amount,
                    "amount_usd": item.amount * item.price,
                }
            )

        return Response(data, status.HTTP_200_OK)


class AssetDebtView(APIView):
    def get(self, request, token_address):
        try:
            asset = MakerAssetDebt.objects.filter(
                token_address__iexact=token_address
            ).latest()
        except MakerAssetDebt.DoesNotExist:
            raise Http404()

        data = []
        for item in asset.positions.all():
            data.append(
                {
                    "symbol": item.underlying_symbol,
                    "amount": item.amount,
                    "amount_usd": item.amount * item.price,
                }
            )

        return Response(data, status.HTTP_200_OK)
