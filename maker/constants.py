# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

DEFISAVER_MCD_SUBSCRIBTION_v2 = "0xc45d4f6b6bf41b6edaa58b01c4298b8d9078269a"

MCD_VAT_CONTRACT_ADDRESS = "0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B"
MCD_VOW_CONTRACT_ADDRESS = "0xA950524441892A31ebddF91d3cEEFa04Bf454466"
MCD_SPOT_CONTRACT_ADDRESS = "0x65C79fcB50Ca1594B025960e539eD7A9a6D434A3"
MCD_JUG_CONTRACT_ADDRESS = "0x19c0976f590D67707E62397C87829d896Dc0f1F1"

MKR_DC_IAM_CONTRACT_ADDRESS = "0xC7Bdd1F2B16447dcf3dE045C4a039A60EC2f0ba3"

AAVE_D3M_CONTRACT_ADDRESS = "0xa13C0c8eB109F5A13c6c90FC26AFb23bEB3Fb04a"

LIQUIDITY_COLLATERAL_ASSET_MAP = {
    "UNIV2DAIETH": ["DAI", "WETH"],
    "UNIV2DAIUSDC": ["DAI", "USDC"],
    "UNIV2UNIETH": ["UNI", "WETH"],
    "UNIV2USDCETH": ["USDC", "WETH"],
    "UNIV2WBTCDAI": ["WBTC", "DAI"],
    "UNIV2WBTCETH": ["WBTC", "WETH"],
    "CRVV1ETHSTETH": ["stETH", "WETH"],
    "GUNIV3DAIUSDC1": ["DAI", "USDC"],
    "GUNIV3DAIUSDC2": ["DAI", "USDC"],
}

SECONDS_PER_YEAR = 31536000

ASSET_TYPE_TOKEN = "token"
ASSET_TYPE_STABLE = "stable"

ASSET_TYPES = (
    (ASSET_TYPE_TOKEN, ASSET_TYPE_TOKEN),
    (ASSET_TYPE_STABLE, ASSET_TYPE_STABLE),
)

CHAINLINK_PROXY_ADDRESSES = {
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": "0x6df09e975c830ecae5bd4ed9d90f3a95a4f88012",
    "0xd46ba6d942050d489dbd938a2c909a5d5039a161": "0x492575fdd11a0fcf2c6c719867890a7648d526eb",
    "0xba100000625a3754423978a60c9317c58a424e3d": "0xc1438aa3823a6ba0c159cfa8d98df5a994ba120b",
    "0x0d8775f648430679a709e98d2b0cb6250d2887ef": "0x0d16d4528239e9ee52fa531af613acdb23d88c94",
    "0x4fabb145d64652a948d72533023f6e7a623c7c53": "0x614715d2af89e6ec99a233818275142ce88d1cfd",
    "0xd533a949740bb3306d119cc777fa900ba034cd52": "0x8a12be339b0cd1829b91adc01977caa5e9ac121e",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "0x773616e4d11a78f511299002da57a0a94577f1f4",
    "0xf629cbd94d3791c9250152bd8dfbdf380e2a3b9c": "0x24d9ab51950f3d62e9144fdc2f3135daa6ce8d1b",
    "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72": "0x5c00128d4d1c2f4f652c267d7bcdd7ac99c16e16",
    "0x956f47f50a910163d8bf957cf5846d573e7f87ca": "0x7f0d2c2838c6ac24443d13e23d99490017bde370",
    "0x853d955acef822db058eb8505911ed77f175b99e": "0x14d04fff8d21bd62987a5ce9ce543d2f1edf5d3e",
    "0x056fd409e1d7a124bd7017459dfea2f387b6d5cd": "0x96d15851cbac05aee4efd9ea3a3dd9bdeec9fc28",
    "0xdd974d5c2e2928dea5f71b9825b8b646686bd200": "0x656c0544ef4c98a6a98491833a89204abb045d6b",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "0xdc530d9457755926550b59e8eccdae7624181557",
    "0x0f5d2fb29fb7d3cfee444a200298f468908cc942": "0x82a44d92d6c329826dc557c5e1be6ebec5d5feb9",
    "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2": "0x24551a8fb2a7211a25a17b1481f043a8a8adc7f2",
    "0x03ab458634910aad20ef5f1c8ee96f1d6ac54919": "0x4ad7B025127e89263242aB68F0f9c4E5C033B489",
    "0x408e41876cccdc0f92210600ef50372656052a38": "0x3147d7203354dc06d9fd350c7a2437bca92387a4",
    "0xd5147bc8e386d91cc5dbe72099dac6c9b99276f5": "0x0606be69451b1c9861ac6b3626b99093b713e801",
    "0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f": "0x79291a9d692df95334b1a0b3b4ae6bc606782f8c",
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "0x86392dc19c0b719886221c78ab11eb8cf5c52812",
    "0x57ab1ec28d129707052df4df418d58a2d46d5f51": "0xad35bd71b9afe6e4bdc266b345c198eadef9ad94",
    "0x0000000000085d4780b73119b644ae5ecd22b376": "0x3886ba987236181d98f2401c507fb8bea7871df2",
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": "0xD6aA3D25116d8dA79Ea0246c4826EB951872e02e",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "0x986b5e1e1755e3c2440e960477f25201b0a8bbd4",
    "0x8e870d67f660d95d5be530380d0ec0bd388289e1": "0x09023c0da49aaf8fc3fa3adf34c6a7016d38d5e3",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "0xee9f2375b4bdf6387aa8265dd4fb8f16512a1d46",
    "0xa693b19d2931d498c5b318df961919bb4aee87a5": "0x8b6d9085f310396c6e4f0012783e9f850eaa8a82",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "0xdeb288f737066589598e9214e782fa5a8ed689e8",
    "0x8798249c2e607446efb7ad49ec89dd1865ff4272": "0x7f59a29507282703b4a796d02cacf23388fff00d",
    "0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e": "0x7c5d4f8345e66f68099581db340cd65b078c41f4",
    "0xe41d2489571d322189246dafa5ebde1f4699f498": "0x2da4983a622a8498bb1a21fae9d8f6c664939962",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419",
    "0x1494ca1f11d487c2bbe4543e90080aeba4ba3c2b": "0x029849bbc0b1d93b85a8b6190e979fd38f5760e2",
    "0xc00e94cb662c3520282e6f5717214004a7f26888": "0x1b39ee86ec5979ba5c322b826b3ecb8c79991699",
    "0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b": "0xd962fc30a72a84ce50161031391756bf2876af5d",
    "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": "0x7bac85a8a13a4bcd8abb3eb7d6b4d632c5a57676",
    "0x6b3595068778dd592e39a122f4f5a5cf09c90fe2": "0xe572cef69f43c2e488b33924af04bdace19079cf",
    "0x111111111117dc0aa78b770fa6a738034120c302": "0x72afaecf99c9d9c8215ff44c77b94b99c28741e8",
    "0x6810e776880c02933d47db1b9fc05908e5386b96": "0xa614953df476577e90dcf4e3428960e221ea4727",
    "0x5f98805a4e8be255a32880fdec7f6728c6568ba0": "0x3d7ae7e594f2f2091ad8798313450130d0aba3a0",
}

OHLCV_TYPE_DAILY = "histoday"
OHLCV_TYPE_HOURLY = "histohour"
OHLCV_TYPES = [
    (OHLCV_TYPE_DAILY, "daily"),
    (OHLCV_TYPE_HOURLY, "hourly"),
]

STABLECOINS = [
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "UST",
    "TUSD",
    "USDP",
    "USDN",
    "FEI",
    "RAI",
    "GUSD",
    "FRAX",
    "LUSD",
    "sUSD",
    "UST",
]

EXCHANGES = {
    "Binance": {"haircut": 100},
    "binanceus": {"haircut": 100},
    "Bitfinex": {"haircut": 100},
    "bitFlyer": {"haircut": 100},
    "Bitstamp": {"haircut": 100},
    "BitTrex": {"haircut": 100},
    "Cexio": {"haircut": 100},
    "Coinbase": {"haircut": 100},
    "itBit": {"haircut": 100},
    "Gemini": {"haircut": 100},
    "Kraken": {"haircut": 100},
    "Luno": {"haircut": 100},
    "Liquid": {"haircut": 100},
    "Poloniex": {"haircut": 100},
    "Bithumb": {"haircut": 50},
    "Coinone": {"haircut": 50},
    "Huobi": {"haircut": 50},
    "OKEX": {"haircut": 50},
    "Upbit": {"haircut": 50},
    "Uniswap": {"haircut": 100},
    "Sushiswap": {"haircut": 100},
    "Curve": {"haircut": 100},
    "UniswapV3": {"haircut": 100},
    "ftx": {"haircut": 100},
    "ftxus": {"haircut": 100},
}

DRAWDOWN_PAIRS_HISTORY_DAYS = {
    "ETH-USD-Coinbase-histohour": 750,
    "BTC-USD-Coinbase-histohour": 750,
    "LINK-USD-Coinbase-histohour": 750,
    "YFI-USD-Coinbase-histohour": 750,
    "UNI-USD-Coinbase-histohour": 750,
    "ZRX-USD-Coinbase-histohour": 750,
    "AAVE-USDT-Binance-histohour": 750,
    "BAT-USDC-Coinbase-histohour": 750,
    "MANA-USDC-Coinbase-histohour": 750,
    "COMP-USD-Coinbase-histohour": 750,
    "BAL-USD-Coinbase-histohour": 750,
    "SUSHI-USDT-Binance-histohour": 750,
    "MATIC-USDT-Binance-histohour": 750,
    "MKR-USD-Coinbase-histohour": 750,
    "ETH-USD-Coinbase-histoday": 2000,
    "BTC-USD-Coinbase-histoday": 2000,
    "LINK-USD-Coinbase-histoday": 2000,
    "YFI-USD-Coinbase-histoday": 2000,
    "UNI-USD-Coinbase-histoday": 2000,
    "ZRX-USD-Coinbase-histoday": 2000,
    "AAVE-USDT-Binance-histoday": 2000,
    "BAT-USDC-Coinbase-histoday": 2000,
    "MANA-USDC-Coinbase-histoday": 2000,
    "COMP-USD-Coinbase-histoday": 2000,
    "BAL-USD-Coinbase-histoday": 2000,
    "SUSHI-USDT-Binance-histoday": 2000,
    "MATIC-USDT-Binance-histoday": 2000,
    "MKR-USD-Coinbase-histoday": 2000,
}


AAVE_TOKEN_ADDRESS = "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9"
WBTC_TOKEN_ADDRESS = "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
WETH_TOKEN_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
DAI_TOKEN_ADDRESS = "0x6B175474E89094C44Da98b954EedeAC495271d0F"
COMP_TOKEN_ADDRESS = "0xc00e94Cb662C3520282E6f5717214004A7f26888"
USDC_TOKEN_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

AWETH_TOKEN_ADDRESS = "0x030bA81f1c18d280636F32af80b9AAd02Cf0854e"
AWBTC_TOKEN_ADDRESS = "0x9ff58f4fFB29fA2266Ab25e75e2A8b3503311656"
