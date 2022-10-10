# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from maker.utils.graphql import run_query


def _fetch_uniswap_v2_pair_day_data(contract_address):
    query = (
        """
        query{
             pairDayDatas(first: 90, skip: 1, orderBy: date, orderDirection: desc,
               where: {
                 pairAddress: "%s",
               }
             ) {
                 date
                 dailyVolumeToken0
                 dailyVolumeToken1
                 dailyVolumeUSD
                 reserveUSD
                 reserve0
                 reserve1
                 totalSupply
                 dailyTxns
                 token0 {
                  symbol
                 }
                 token1 {
                  symbol
                 }
             }
        }
    """
        % contract_address
    )
    url = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2"
    response = run_query(url, query)
    data = []
    for pair in response["data"]["pairDayDatas"]:
        data.append(
            {
                "date": pair["date"],
                "token_0_symbol": pair["token0"]["symbol"],
                "token_1_symbol": pair["token1"]["symbol"],
                "reserve_0": pair["reserve0"],
                "reserve_1": pair["reserve1"],
                "volume_token_0": pair["dailyVolumeToken0"],
                "volume_token_1": pair["dailyVolumeToken1"],
                "total_supply": pair["totalSupply"],
                "reserve_USD": pair["reserveUSD"],
                "volume_USD": pair["dailyVolumeUSD"],
                "tx_count": pair["dailyTxns"],
            }
        )
    return data


def _fetch_uniswap_v3_pair_day_data(contract_address):
    query = (
        """
        query{
            poolDayDatas(first: 90, skip: 1, orderBy: date, orderDirection: desc,
              where: {
                pool: "%s"
              }
            ) {
                date
                volumeToken0
                volumeToken1
                volumeUSD
                token0Price
                token1Price
                txCount
                tvlUSD
                pool {
                  token0 {
                    symbol
                  }
                  token1 {
                    symbol
                  }
                }
            }
        }
    """
        % contract_address
    )
    url = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
    response = run_query(url, query)
    data = []
    for pair in response["data"]["poolDayDatas"]:
        data.append(
            {
                "date": pair["date"],
                "token_0_symbol": pair["pool"]["token0"]["symbol"],
                "token_1_symbol": pair["pool"]["token1"]["symbol"],
                "reserve_0": pair["token0Price"],
                "reserve_1": pair["token1Price"],
                "volume_token_0": pair["volumeToken0"],
                "volume_token_1": pair["volumeToken1"],
                "volume_USD": pair["volumeUSD"],
                "tx_count": pair["txCount"],
                "reserve_USD": pair["tvlUSD"],
                "total_supply": None,
            }
        )
    return data


def _fetch_sushiswap_pair_day_data(contract_address):
    query = (
        """
        query{
             pairDayDatas(first:90, skip: 1, orderBy: date, orderDirection: desc,
               where: {
                 pair: "%s"
               }
             ) {
                 date
                 volumeToken0
                 volumeToken1
                 volumeUSD
                 reserveUSD
                 reserve0
                 reserve1
                 totalSupply
                 txCount
                 token0 {
                  symbol
                 }
                 token1 {
                  symbol
                 }
             }
        }
    """
        % contract_address
    )

    url = "https://api.thegraph.com/subgraphs/name/sushiswap/exchange"
    response = run_query(url, query)
    data = []
    for pair in response["data"]["pairDayDatas"]:
        data.append(
            {
                "date": pair["date"],
                "token_0_symbol": pair["token0"]["symbol"],
                "token_1_symbol": pair["token1"]["symbol"],
                "reserve_0": pair["reserve0"],
                "reserve_1": pair["reserve1"],
                "volume_token_0": pair["volumeToken0"],
                "volume_token_1": pair["volumeToken1"],
                "total_supply": pair["totalSupply"],
                "reserve_USD": pair["reserveUSD"],
                "volume_USD": pair["volumeUSD"],
                "tx_count": pair["txCount"],
            }
        )
    return data


def get_pair_day_data(contract_address, exchange):
    if exchange.lower() == "uniswap":
        return _fetch_uniswap_v2_pair_day_data(contract_address)

    if exchange.lower() == "uniswapv3":
        return _fetch_uniswap_v3_pair_day_data(contract_address)

    elif exchange.lower() == "sushiswap":
        return _fetch_sushiswap_pair_day_data(contract_address)


def get_pair_day_data_curve(contract_address):
    query = """
        query{
             pools(where: {id: "<contract_address>"}) {
                id,
                locked,
                dailyVolumes(first: 90, skip: 1, orderBy: timestamp, orderDirection: desc) {
                    id
                    timestamp
                    volume
                }
                coins {
                    id
                balance
                token {
                    id
                    symbol
                    }
                }
             }
        }
    """
    url = "https://api.thegraph.com/subgraphs/name/sistemico/curve"
    query = query.replace("<contract_address>", contract_address.lower())
    data = run_query(url, query)
    return data["data"]["pools"]
