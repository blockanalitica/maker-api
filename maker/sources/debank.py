from django.conf import settings

from maker.utils.http import retry_get_json

DEBANK_API_URL = "https://pro-openapi.debank.com/v1/"


def fetch_user_token_list(wallet_address):
    url = f"user/token_list?id={wallet_address}&chain_id=eth&is_all=false"
    data = retry_get_json(
        "{}{}".format(DEBANK_API_URL, url),
        headers={"AccessKey": settings.DEBANK_API_KEY},
    )
    return data


"""
 {'id': 'eth',
  'chain': 'eth',
  'name': 'ETH',
  'symbol': 'ETH',
  'display_symbol': None,
  'optimized_symbol': 'ETH',
  'decimals': 18,
  'logo_url': 'https://static.debank.com/image/token/logo_url/eth/935ae4e4d1d12d59a99717a24f2540b5.png',
  'protocol_id': '',
  'price': 1624.79,
  'is_verified': True,
  'is_core': True,
  'is_wallet': True,
  'time_at': 1483200000.0,
  'amount': 3442.2988255541986,
  'raw_amount': 3442298825554198670666,
  'raw_amount_hex_str': '0xba9b7e1fc2be5a2d4a'}
"""
