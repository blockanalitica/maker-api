# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from decimal import Decimal

import pytest

from maker.models import SlippageDaily
from maker.modules.slippage import save_oneinch_slippages, save_zerox_slippages
from tests.maker.factories import AssetFactory, SlippagePairFactory


@pytest.mark.django_db
def test_save_oneinch_slippages(responses):
    from_asset = AssetFactory(price=Decimal("200"))
    slippage_pair = SlippagePairFactory(from_asset=from_asset)
    mantisa = 10**from_asset.decimals
    amount = 50 * mantisa

    to_token_amount = str(
        int((amount * slippage_pair.from_asset.price) * Decimal("0.09"))
    )
    quote = {"toTokenAmount": to_token_amount}
    oneinch = (
        f"https://api.1inch.io/v4.1/1/quote?"
        f"fromTokenAddress={slippage_pair.from_asset.address}"
        f"&toTokenAddress={slippage_pair.to_asset.address}&amount={amount}"
    )
    responses.add(responses.GET, oneinch, status=200, json=quote)

    save_oneinch_slippages(slippage_pair.id)

    slippage_daily = SlippageDaily.objects.get(pair=slippage_pair).slippage_percent_avg
    assert slippage_daily == Decimal("-91.0000")


@pytest.mark.django_db
def test_save_zerox_slippages(responses):
    from_asset = AssetFactory(price=Decimal("200"))
    slippage_pair = SlippagePairFactory(from_asset=from_asset)
    asset_price = from_asset.price
    mantisa = 10**from_asset.decimals
    amount = 50 * mantisa
    price = str(int(asset_price - (Decimal("0.91") * asset_price)))
    quote = {"price": price}
    zerox = (
        f"https://api.0x.org/swap/v1/quote?"
        f"buyToken={slippage_pair.to_asset.address}"
        f"&sellToken={slippage_pair.from_asset.address}&sellAmount={amount}"
    )
    responses.add(responses.GET, zerox, status=200, json=quote)

    save_zerox_slippages(slippage_pair)

    slippage_daily = SlippageDaily.objects.get(pair=slippage_pair).slippage_percent_avg
    assert slippage_daily == Decimal("-91.0000")
