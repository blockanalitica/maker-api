# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

from django.conf import settings

from maker.utils.blockchain.chain import Blockchain
from maker.utils.metrics import auto_named_statsd_timer

from ..models import Block


def save_latest_blocks():
    chain = Blockchain(node=settings.ETH_NODE_MAKER)
    latest_chain_block = chain.get_latest_block()
    try:
        latest_db_block = Block.objects.latest().block_number
    except Block.DoesNotExist:
        latest_db_block = latest_chain_block - 1

    for block_number in range(latest_db_block, latest_chain_block):
        block_info = chain.get_block_info(block_number)
        Block.objects.get_or_create(
            block_number=block_number,
            defaults=dict(
                timestamp=block_info.timestamp,
                datetime=datetime.fromtimestamp(block_info.timestamp),
            ),
        )


@auto_named_statsd_timer
def get_or_save_block(block_number):
    try:
        block = Block.objects.get(block_number=block_number)
    except Block.DoesNotExist:
        chain = Blockchain()
        block_info = chain.get_block_info(block_number)
        block_timestamp = block_info.timestamp
        block, _ = Block.objects.get_or_create(
            block_number=block_number,
            defaults=dict(
                timestamp=block_timestamp,
                datetime=datetime.fromtimestamp(block_timestamp),
            ),
        )
    return block
