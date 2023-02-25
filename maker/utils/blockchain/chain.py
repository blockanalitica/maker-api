# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from decimal import Decimal

import requests
from django.conf import settings
from multicall import Call, Multicall
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from web3 import Web3

from maker.utils.metrics import auto_named_statsd_timer

log = logging.getLogger(__name__)


class Blockchain:
    def __init__(self, node=settings.ETH_NODE, _web3=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._node_address = node
        if isinstance(_web3, Blockchain):
            self._web3 = _web3.web3
        else:
            self._web3 = _web3
        self._abis = {}

    @property
    def web3(self):
        if not self._web3:
            session = requests.Session()
            retries = 3
            retry = Retry(
                total=retries,
                read=retries,
                connect=retries,
                backoff_factor=0.5,
                status_forcelist=(429,),
                respect_retry_after_header=True,
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            self._web3 = Web3(
                Web3.HTTPProvider(
                    self._node_address, request_kwargs={"timeout": 60}, session=session
                )
            )
        return self._web3

    @property
    def eth(self):
        return self.web3.eth

    def get_block_info(self, block_number):
        return self.eth.get_block(block_number)

    def get_latest_block(self):
        return self.eth.blockNumber

    def _load_abi(self, token_address):
        if token_address not in self._abis:
            with open(
                "./maker/utils/blockchain/abis/{}.json".format(token_address), "r"
            ) as f:
                self._abis[token_address] = json.loads(f.read())
        return self._abis[token_address]

    def get_contract(self, token_address, abi_type=None):
        token_address = Web3.toChecksumAddress(token_address)
        if abi_type:
            abi = self._load_abi(abi_type)
        else:
            abi = self._load_abi(token_address)
        return self.web3.eth.contract(address=token_address, abi=abi)

    def get_balance_of(self, token_address, wallet_address, block_number=None):
        """
        Helper function for getting balance from a wallet.
        It converts the balance into Decimal.
        """
        if not block_number:
            block_number = "latest"
        token_address = Web3.toChecksumAddress(token_address)
        contract = self.get_contract(token_address, abi_type="erc20")
        wallet_address = Web3.toChecksumAddress(wallet_address)
        balance = contract.functions.balanceOf(wallet_address).call(
            block_identifier=block_number
        )
        return Decimal(balance)

    def get_total_supply(self, token_address):
        """
        Helper function for getting total supply of a token.
        It converts the total supply into Decimal.
        """
        token_address = Web3.toChecksumAddress(token_address)
        contract = self.get_contract(token_address)
        total_supply = contract.caller.totalSupply()
        return Decimal(total_supply)

    def get_storage_at(self, token_address, position, block_identifier=None):
        """
        Helper function to get stored data from contract
        """
        token_address = Web3.toChecksumAddress(token_address)
        content = self.eth.get_storage_at(
            token_address, position, block_identifier=block_identifier
        ).hex()
        return content

    def get_first_block(self, token_address, from_block=0, to_block="latest"):
        token_address = Web3.toChecksumAddress(token_address)
        contract = self.get_contract(token_address, abi_type="ceth")
        return self.get_new_comptroller_events(contract, from_block, to_block)

    def covert_to_number(self, hex_values):
        """
        Helper function to get number from hex value
        """
        return Decimal(int(hex_values[34:], 16))

    def to_hex_topic(self, topic):
        return Web3.keccak(text=topic).hex()

    @auto_named_statsd_timer
    def call_multicall(self, calls, block_id=None):
        multicalls = []
        for address, function, response in calls:
            multicalls.append(Call(address, function, [response]))

        multi = Multicall(multicalls, _w3=self.web3, block_id=block_id)

        return multi()

    def convert_ray(self, ray):
        """
        Helper function to get decimal number from ray
        """
        return Decimal(ray) / 10**27
