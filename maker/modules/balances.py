# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from decimal import Decimal

from django_bulk_load import bulk_insert_models

from maker.models import Vault, WalletExternalProtocol, WalletTokenBalance
from maker.sources.debank import fetch_user_protocols, fetch_user_token_list


def get_vaults_wallet_addresses(debt_limit=1000):
    wallet_addresses = Vault.objects.filter(
        debt__gte=debt_limit,
        owner_address__isnull=False,
    ).values_list("owner_address", flat=True)
    return wallet_addresses


def save_balances(wallet_addresses):
    dt = datetime.now()
    for wallet_address in wallet_addresses:
        bulk_create = []
        data = fetch_user_token_list(wallet_address)
        for entry in data:
            usd_amount = Decimal(entry["amount"]) * Decimal(entry["price"])
            if usd_amount > 500:
                bulk_create.append(
                    WalletTokenBalance(
                        wallet_address=wallet_address,
                        amount=entry["amount"],
                        symbol=entry["optimized_symbol"],
                        price=entry["price"],
                        usd_amount=Decimal(entry["amount"]) * Decimal(entry["price"]),
                        datetime=dt,
                        chain=entry["chain"],
                    )
                )
        if bulk_create:
            bulk_insert_models(bulk_create)


def save_protocols(wallet_addresses):
    dt = datetime.now()
    for wallet_address in wallet_addresses:
        bulk_create = []
        data = fetch_user_protocols(wallet_address)
        for entry in data:
            if entry["net_usd_value"] > 1000:
                bulk_create.append(
                    WalletExternalProtocol(
                        wallet_address=wallet_address,
                        protocol=entry["id"],
                        protocol_name=entry["name"],
                        chain=entry["chain"],
                        net_usd_value=entry["net_usd_value"],
                        debt_usd_value=entry["debt_usd_value"],
                        datetime=dt,
                    )
                )
        if bulk_create:
            bulk_insert_models(bulk_create)


def sync_wallet_balances():
    wallet_addresses = get_vaults_wallet_addresses()
    wallet_addresses = set(wallet_addresses)
    save_balances(wallet_addresses)


def sync_save_protocols():
    wallet_addresses = get_vaults_wallet_addresses()
    wallet_addresses = set(wallet_addresses)
    save_protocols(wallet_addresses)
