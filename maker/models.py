# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0
from autoslug import AutoSlugField
from django.contrib.postgres.fields import ArrayField
from django.db import models
from model_utils.models import TimeStampedModel, UUIDModel

from .constants import ASSET_TYPES, OHLCV_TYPE_DAILY, OHLCV_TYPES


class MakerBackedToken(TimeStampedModel):
    date = models.DateField()
    timestamp = models.IntegerField()
    token_address = models.CharField(max_length=42, db_index=True)
    underlying_symbol = models.CharField(max_length=16)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("timestamp",)


class MakerBackedTokenPosition(TimeStampedModel):
    backed_token = models.ForeignKey(
        MakerBackedToken, on_delete=models.CASCADE, related_name="positions"
    )
    token_address = models.CharField(max_length=42, db_index=True)
    underlying_symbol = models.CharField(max_length=16)

    total = models.DecimalField(max_digits=20, decimal_places=6)
    share = models.DecimalField(max_digits=10, decimal_places=6)


class MakerAssetCollateral(TimeStampedModel):
    timestamp = models.IntegerField()
    token_address = models.CharField(max_length=42, db_index=True)
    underlying_symbol = models.CharField(max_length=16)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)


class MakerAssetCollateralDebt(TimeStampedModel):
    asset = models.ForeignKey(
        MakerAssetCollateral, on_delete=models.CASCADE, related_name="positions"
    )
    timestamp = models.IntegerField()
    token_address = models.CharField(max_length=42, db_index=True)
    underlying_symbol = models.CharField(max_length=16, db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=6)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)


class MakerAssetDebt(TimeStampedModel):
    timestamp = models.IntegerField()
    token_address = models.CharField(max_length=42, db_index=True)
    underlying_symbol = models.CharField(max_length=16)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)


class MakerAssetDebtCollateral(TimeStampedModel):
    asset = models.ForeignKey(
        MakerAssetDebt, on_delete=models.CASCADE, related_name="positions"
    )
    timestamp = models.IntegerField(null=True)
    token_address = models.CharField(max_length=42, db_index=True)
    underlying_symbol = models.CharField(max_length=16, db_index=True)
    amount = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=6)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)


class MakerAsset(TimeStampedModel):
    symbol = models.CharField(max_length=64, db_index=True, unique=True)
    address = models.CharField(max_length=42, null=True)
    oracle_address = models.CharField(max_length=42, null=True)
    medianizer_address = models.CharField(max_length=42, null=True)
    type = models.CharField(max_length=32)
    is_active = models.BooleanField(default=True, null=True)
    is_stable = models.BooleanField(default=False, null=True)

    def __repr__(self):
        return f"<{self.__class__.__name__}: symbol={self.symbol}>"


class ILKManager(models.Manager):
    def active(self):
        return self.filter(type__in=["asset", "lp"], is_active=True)

    def assets(self):
        return self.filter(type="asset", is_active=True)

    def with_vaults(self):
        return self.filter(
            type__in=["asset", "lp", "stable", "lp-stable"], is_active=True
        )


class Ilk(TimeStampedModel):
    ilk = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=64)
    collateral = models.CharField(max_length=64, null=True)
    dai_debt = models.DecimalField(max_digits=32, decimal_places=18)
    debt_ceiling = models.DecimalField(max_digits=32, decimal_places=18)
    dc_iam_line = models.BigIntegerField(null=True)
    dc_iam_gap = models.BigIntegerField(null=True)
    dc_iam_ttl = models.BigIntegerField(null=True)
    lr = models.DecimalField(decimal_places=4, max_digits=8, null=True)
    locked = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    osm_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    osm_price_next = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    dust = models.BigIntegerField(null=True)
    stability_fee = models.DecimalField(max_digits=8, decimal_places=4, null=True)

    chop = models.DecimalField(null=True, decimal_places=4, max_digits=8)
    hole = models.BigIntegerField(null=True)
    buf = models.DecimalField(null=True, decimal_places=4, max_digits=8)
    tail = models.BigIntegerField(null=True)
    cusp = models.DecimalField(null=True, decimal_places=4, max_digits=8)
    chip = models.DecimalField(null=True, decimal_places=4, max_digits=8)
    tip = models.BigIntegerField(null=True)
    step = models.BigIntegerField(null=True)
    cut = models.DecimalField(null=True, decimal_places=4, max_digits=8)

    fee_in = models.BigIntegerField(null=True)
    fee_out = models.BigIntegerField(null=True)

    timestamp = models.BigIntegerField()
    type = models.CharField(max_length=32)

    has_liquidations = models.BooleanField(null=True)

    is_active = models.BooleanField(default=True, null=True)
    is_stable = models.BooleanField(default=False, null=True)

    capital_at_risk = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    total_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    risk_premium = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    vaults_count = models.IntegerField(null=True)

    objects = ILKManager()

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)

    def __str__(self):
        return self.ilk

    def __repr__(self):
        return f"<{self.__class__.__name__}: ilk={self.ilk}>"


class VaultManager(models.Manager):
    def active(self):
        return self.filter(debt__gte=5000, is_active=True)


class Vault(TimeStampedModel):
    uid = models.CharField(max_length=42, db_index=True)
    urn = models.CharField(max_length=42)
    ilk = models.CharField(max_length=32, db_index=True)
    collateral_symbol = models.CharField(max_length=32, null=True)
    collateral = models.DecimalField(max_digits=32, decimal_places=18)
    art = models.DecimalField(max_digits=32, decimal_places=0)
    debt = models.DecimalField(max_digits=32, decimal_places=18)
    principal = models.DecimalField(max_digits=32, decimal_places=18)
    accrued_fees = models.DecimalField(max_digits=32, decimal_places=18)
    paid_fees = models.DecimalField(max_digits=32, decimal_places=18)
    collateralization = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    osm_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    mkt_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    ratio = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    liquidation_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    available_collateral = models.DecimalField(max_digits=32, decimal_places=18)
    available_debt = models.DecimalField(max_digits=32, decimal_places=18)
    owner_address = models.CharField(max_length=42, null=True)
    owner_ens = models.CharField(max_length=64, null=True)
    ds_proxy_address = models.CharField(max_length=42, null=True)
    block_created = models.IntegerField()
    block_number = models.IntegerField(null=True)
    block_timestamp = models.IntegerField(null=True)
    block_datetime = models.DateTimeField(null=True)

    is_active = models.BooleanField(default=True, db_index=True)
    timestamp = models.IntegerField(null=True, help_text="Run timestamp")
    datetime = models.DateTimeField(null=True)
    protection_service = models.CharField(max_length=64, null=True)
    protection_score = models.CharField(max_length=10, null=True)

    is_at_risk = models.BooleanField(null=True, default=False)
    is_at_risk_market = models.BooleanField(null=True, default=False)

    collateral_change_1d = models.DecimalField(
        max_digits=32, decimal_places=18, null=True, default=0
    )
    collateral_change_7d = models.DecimalField(
        max_digits=32, decimal_places=18, null=True, default=0
    )
    collateral_change_30d = models.DecimalField(
        max_digits=32, decimal_places=18, null=True, default=0
    )
    principal_change_1d = models.DecimalField(
        max_digits=32, decimal_places=18, null=True, default=0
    )
    principal_change_7d = models.DecimalField(
        max_digits=32, decimal_places=18, null=True, default=0
    )
    principal_change_30d = models.DecimalField(
        max_digits=32, decimal_places=18, null=True, default=0
    )

    liquidation_drop = models.DecimalField(max_digits=4, decimal_places=2, null=True)
    is_institution = models.BooleanField(null=True, default=False)
    owner_name = models.CharField(max_length=64, null=True)

    last_activity = models.DateTimeField(null=True)

    objects = VaultManager()

    class Meta:
        get_latest_by = "timestamp"
        indexes = [
            models.Index(fields=["ilk", "is_active"]),
        ]
        unique_together = ["uid", "ilk"]

    def __repr__(self):
        return f"<{self.__class__.__name__}: uid={self.uid}, ilk={self.ilk}>"


class RawEvent(TimeStampedModel):
    block_number = models.IntegerField(db_index=True)
    timestamp = models.BigIntegerField()
    datetime = models.DateTimeField(db_index=True)
    tx_hash = models.CharField(max_length=128)
    vault_uid = models.CharField(max_length=64, null=True, db_index=True)
    ilk = models.CharField(max_length=32, db_index=True)
    operation = models.CharField(max_length=64)
    collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    principal = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    fees = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    mkt_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    osm_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    art = models.DecimalField(max_digits=32, decimal_places=0, null=True)
    rate = models.DecimalField(max_digits=32, decimal_places=0, null=True)

    index = models.CharField(max_length=128, null=True)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)
        unique_together = [
            "block_number",
            "tx_hash",
            "vault_uid",
            "ilk",
            "operation",
            "index",
            "collateral",
            "principal",
            "fees",
        ]


class OSMManager(models.Manager):
    def latest_for_asset(self, symbol):
        return self.filter(symbol=symbol).latest()

    def latest_for_all_assets(self):
        # We select only OSM (with related asset) without any filtering and custom
        # ordering to use the index, as otherwise distinct is taking aaaaages.
        # Only once we select the whole thing, we order OSM's by asset symbol.
        osms = self.order_by("symbol", "-block_number").distinct("symbol")
        return sorted(list(osms), key=lambda x: x.symbol)


class OSM(TimeStampedModel):
    symbol = models.CharField(max_length=64, db_index=True)
    current_price = models.DecimalField(max_digits=32, decimal_places=18)
    next_price = models.DecimalField(max_digits=32, decimal_places=18)
    block_number = models.IntegerField()
    timestamp = models.IntegerField(null=True)
    datetime = models.DateTimeField()

    objects = OSMManager()

    class Meta:
        get_latest_by = "block_number"
        ordering = ["-block_number"]
        indexes = [
            models.Index(fields=["symbol", "-block_number"]),
        ]


class Medianizer(models.Model):
    symbol = models.CharField(max_length=32, db_index=True)
    price = models.DecimalField(max_digits=32, decimal_places=18)
    block_number = models.IntegerField(db_index=True)
    timestamp = models.IntegerField()
    datetime = models.DateTimeField()

    class Meta:
        get_latest_by = "block_number"
        ordering = ("block_number",)
        unique_together = ["symbol", "block_number"]


class VaultsLiquidation(TimeStampedModel):
    ilk = models.CharField(max_length=32)
    drop = models.IntegerField(db_index=True)
    cr = models.DecimalField(max_digits=32, decimal_places=18)
    total_debt = models.DecimalField(max_digits=32, decimal_places=18)
    debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    current_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    expected_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    type = models.CharField(max_length=32, null=True, db_index=True)

    class Meta:
        get_latest_by = "created"


class IlkHistoricStats(TimeStampedModel):
    ilk = models.CharField(max_length=32)
    timestamp = models.IntegerField()
    datetime = models.DateTimeField(db_index=True)
    total_debt = models.DecimalField(max_digits=32, decimal_places=18)
    vaults_count = models.IntegerField(null=True)
    weighted_collateralization_ratio = models.DecimalField(
        max_digits=8, decimal_places=2, null=True
    )
    total_locked = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    protected_count = models.IntegerField(null=True)
    protected_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    capital_at_risk = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    risk_premium = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    capital_at_risk_7d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    risk_premium_7d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    capital_at_risk_30d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    risk_premium_30d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )

    class Meta:
        get_latest_by = "datetime"


class IlkHistoricParams(TimeStampedModel):
    ilk = models.CharField(max_length=42, db_index=True)
    block_number = models.IntegerField()
    timestamp = models.IntegerField()
    type = models.CharField(max_length=32)
    lr = models.IntegerField(null=True)
    stability_fee = models.DecimalField(max_digits=20, decimal_places=18, null=True)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["timestamp"]


class VaultEventState(TimeStampedModel):
    block_number = models.IntegerField()
    timestamp = models.BigIntegerField()
    datetime = models.DateTimeField(null=True)
    tx_hash = models.CharField(max_length=128)
    vault_uid = models.CharField(max_length=64, null=True, db_index=True)
    ilk = models.CharField(max_length=32, db_index=True)
    operation = models.CharField(max_length=64)
    human_operation = models.CharField(max_length=64, null=True)
    collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    before_collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    after_collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    principal = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    before_principal = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    after_principal = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    before_ratio = models.DecimalField(max_digits=32, decimal_places=3, null=True)
    after_ratio = models.DecimalField(max_digits=32, decimal_places=3, null=True)
    fees = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    osm_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    rate = models.DecimalField(max_digits=32, decimal_places=0, null=True)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("-timestamp",)
        unique_together = [
            "tx_hash",
            "vault_uid",
        ]


class D3M(TimeStampedModel):
    timestamp = models.IntegerField()
    datetime = models.DateTimeField()
    debt_ceiling = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    block_number = models.IntegerField()
    max_debt_ceiling = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    target_borrow_rate = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )

    balance = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    protocol = models.CharField(max_length=32)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["-timestamp"]


class SurplusBuffer(TimeStampedModel):
    timestamp = models.IntegerField()
    datetime = models.DateTimeField()
    amount = models.DecimalField(max_digits=20, decimal_places=8)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["timestamp"]


class OverallStat(TimeStampedModel):
    timestamp = models.IntegerField()
    datetime = models.DateTimeField(db_index=True)
    total_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    total_risky_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    total_stable_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    surplus_buffer = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    capital_at_risk = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    capital_at_risk_7d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    capital_at_risk_30d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    high_risk = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    medium_risk = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    low_risk = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    vault_count = models.IntegerField(null=True)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["timestamp"]


class RiskPremium(TimeStampedModel):
    ilk = models.CharField(max_length=64, db_index=True)
    timestamp = models.IntegerField(null=True)
    datetime = models.DateTimeField(null=True, db_index=True)
    jump_severity = models.FloatField()
    jump_frequency = models.IntegerField()
    keeper_profit = models.FloatField()
    data = models.JSONField(null=True)
    share_vaults_protected = models.FloatField()
    risk_premium = models.DecimalField(max_digits=32, decimal_places=18)
    risk_premium_7d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    risk_premium_30d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    debt_ceiling = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    debt_ceiling_7d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    debt_ceiling_30d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    total_debt_dai = models.DecimalField(max_digits=32, decimal_places=18)
    capital_at_risk = models.DecimalField(max_digits=32, decimal_places=18)
    capital_at_risk_7d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    capital_at_risk_30d_avg = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    high_risk_debt = models.DecimalField(max_digits=32, decimal_places=18)
    medium_risk_debt = models.DecimalField(max_digits=32, decimal_places=18)
    low_risk_debt = models.DecimalField(max_digits=32, decimal_places=18)
    collateralization_ratio = models.DecimalField(
        max_digits=8, decimal_places=4, null=True
    )

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["-timestamp"]


class VaultProtectionScore(TimeStampedModel):
    vault_uid = models.CharField(max_length=64)
    ilk = models.CharField(max_length=64, null=True)
    timestamp = models.IntegerField()
    datetime = models.DateTimeField()
    cur_cr = models.FloatField()
    total_debt_dai = models.FloatField()
    protection_service = models.BooleanField()
    cur_lr = models.FloatField()
    cr_increase_actions = models.FloatField()
    unique_price_drop_days_protected = models.FloatField()
    cr_increase_actions_5 = models.IntegerField()
    cr_increase_actions_10 = models.IntegerField()
    cr_increase_actions_15 = models.IntegerField()
    unique_price_drop_days_protected_1 = models.IntegerField(null=True)
    unique_price_drop_days_protected_2 = models.IntegerField(null=True)
    unique_price_drop_days_protected_3 = models.IntegerField(null=True)
    unique_price_drop_days_protected_5 = models.IntegerField(null=True)
    cur_cr_risk_1_5x = models.IntegerField()
    cur_cr_risk_2x = models.IntegerField()
    cur_cr_risk_3x = models.IntegerField()
    protection_score = models.CharField(max_length=10)
    unique_actions_7d = models.IntegerField(null=True)
    unique_actions_30d = models.IntegerField(null=True)
    unique_actions_90d = models.IntegerField(null=True)
    unique_actions_7d_15 = models.IntegerField(null=True)
    unique_actions_30d_15 = models.IntegerField(null=True)
    unique_actions_90d_15 = models.IntegerField(null=True)
    unique_actions_7d_10 = models.IntegerField(null=True)
    unique_actions_30d_10 = models.IntegerField(null=True)
    unique_actions_90d_10 = models.IntegerField(null=True)
    volatility_actions_30d_low = models.IntegerField(null=True)
    volatility_actions_30d_medium = models.IntegerField(null=True)
    liquidation_protections = models.FloatField(null=True)
    liquidation_protections_1 = models.FloatField(null=True)
    liquidation_protections_2 = models.FloatField(null=True)
    liquidation_protections_3 = models.FloatField(null=True)
    liquidation_protections_5 = models.FloatField(null=True)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["timestamp"]
        unique_together = [
            "vault_uid",
            "ilk",
            "timestamp",
        ]


class VaultOwnerGroup(TimeStampedModel):
    name = models.CharField(max_length=256)
    slug = AutoSlugField(populate_from="name", unique=True)
    tags = ArrayField(models.CharField(max_length=20), default=list, blank=True)

    def __repr__(self):
        return f"<{self.__class__.__name__}: name={self.name} slug={self.slug}>"

    def __str__(self):
        return self.slug


class VaultOwner(TimeStampedModel):
    address = models.CharField(max_length=42, unique=True)
    name = models.CharField(max_length=256, null=True, blank=True)
    ens = models.CharField(max_length=64, null=True)
    tags = ArrayField(models.CharField(max_length=20), default=list, blank=True)
    group = models.ForeignKey(
        "VaultOwnerGroup", on_delete=models.CASCADE, related_name="addresses", null=True
    )

    def __repr__(self):
        return f"<{self.__class__.__name__}: address={self.address} name={self.name}>"

    def __str__(self):
        return self.address


class VaultsLiquidationHistory(TimeStampedModel):
    ilk = models.CharField(max_length=32)
    drop = models.IntegerField()
    cr = models.DecimalField(max_digits=32, decimal_places=18)
    debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    total_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    current_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    expected_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    type = models.CharField(max_length=32, null=True)
    timestamp = models.IntegerField(db_index=True)
    datetime = models.DateTimeField(db_index=True)

    class Meta:
        get_latest_by = "timestamp"
        unique_together = ["ilk", "drop", "timestamp", "type"]


class Auction(TimeStampedModel):
    ilk = models.CharField(max_length=32, db_index=True)
    symbol = models.CharField(max_length=32, null=True)
    uid = models.IntegerField()
    auction_start = models.DateTimeField(null=True)
    vault = models.CharField(max_length=32, null=True)
    urn = models.CharField(max_length=64, null=True)
    owner = models.CharField(max_length=64, null=True)
    debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    debt_liquidated = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    available_collateral = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    kicked_collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    penalty = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    penalty_fee = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    sold_collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    recovered_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    round = models.IntegerField(null=True)
    auction_end = models.DateTimeField(null=True)
    finished = models.IntegerField(null=True)
    duration = models.IntegerField(null=True)
    avg_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    osm_settled_avg = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    mkt_settled_avg = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    class Meta:
        get_latest_by = "uid"
        ordering = ["uid"]

    def __repr__(self):
        return f"<{self.__class__.__name__}: ilk={self.ilk}, uid={self.uid}>"


class AuctionAction(TimeStampedModel):
    uid = models.IntegerField(null=True)
    auction_uid = models.IntegerField(null=True)
    auction = models.ForeignKey(
        Auction, on_delete=models.CASCADE, related_name="actions", null=True
    )
    ilk = models.CharField(max_length=32)
    datetime = models.DateTimeField(null=True)
    debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    available_collateral = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )

    sold_collateral = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    recovered_debt = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    round = models.IntegerField(null=True)
    type = models.CharField(max_length=16)
    collateral_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    init_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    osm_price = models.DecimalField(max_digits=32, decimal_places=18)
    mkt_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    keeper = models.CharField(max_length=64, null=True)
    incentives = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    status = models.IntegerField()
    caller = models.CharField(max_length=64, null=True)

    closing_take = models.IntegerField(null=True)
    gas_used = models.BigIntegerField(null=True)

    tx_hash = models.CharField(max_length=128, null=True)
    urn = models.CharField(max_length=42, null=True)
    block_number = models.BigIntegerField(null=True)

    class Meta:
        get_latest_by = "datetime"
        ordering = ["uid"]


class GasPrice(TimeStampedModel):
    timestamp = models.BigIntegerField()
    datetime = models.DateTimeField(null=True)
    rapid = models.BigIntegerField()
    fast = models.BigIntegerField()
    standard = models.BigIntegerField()
    slow = models.BigIntegerField()
    eth_price = models.DecimalField(max_digits=10, decimal_places=4, null=True)

    class Meta:
        get_latest_by = "timestamp"


class LiquidityScore(TimeStampedModel):
    symbol = models.CharField(max_length=32, null=True)
    date = models.DateField()
    score = models.IntegerField()
    debt_exposure = models.DecimalField(max_digits=32, decimal_places=18)
    over_time = models.JSONField()

    class Meta:
        get_latest_by = "date"
        unique_together = ["date", "symbol"]


class Rates(TimeStampedModel):
    symbol = models.CharField(max_length=32)
    eth_rate = models.DecimalField(max_digits=32, decimal_places=18)
    eth_reward_rate = models.DecimalField(max_digits=32, decimal_places=18)
    borrow_rate = models.DecimalField(max_digits=32, decimal_places=18)
    rewards_rate = models.DecimalField(max_digits=32, decimal_places=18)
    protocol = models.CharField(max_length=32)

    datetime = models.DateTimeField()

    class Meta:
        get_latest_by = "datetime"
        ordering = ["-datetime"]


class MonthlyDaiSupply(TimeStampedModel):
    report_date = models.DateField()
    cohort_date = models.DateField()
    ilk = models.CharField(max_length=64)
    vault_uid = models.CharField(max_length=64)
    tenure = models.IntegerField()
    tenure_category = models.CharField(max_length=10)
    dai_supply = models.DecimalField(max_digits=32, decimal_places=18)

    class Meta:
        get_latest_by = "report_date"
        ordering = ["-report_date"]
        unique_together = ["report_date", "ilk", "vault_uid"]


class PeriodicalDaiSupplyGrowth(TimeStampedModel):
    time_period = models.CharField(max_length=10)
    ilk = models.CharField(max_length=64)
    demand_growth = models.DecimalField(max_digits=32, decimal_places=18)
    debt_weighted_demand_growth_perc = models.DecimalField(
        max_digits=10, decimal_places=5
    )

    class Meta:
        unique_together = ["time_period", "ilk"]


class DAITrade(TimeStampedModel):
    timestamp = models.DecimalField(max_digits=13, decimal_places=3, db_index=True)
    datetime = models.DateTimeField(db_index=True)
    pair = models.CharField(max_length=10, db_index=True)
    exchange = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=32, decimal_places=18)
    price = models.DecimalField(max_digits=32, decimal_places=18)
    dai_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    dai_amount = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    class Meta:
        ordering = ["-datetime"]


class ForumPost(TimeStampedModel):
    segments = ArrayField(models.CharField(max_length=128), blank=True, null=True)
    vault_types = ArrayField(models.CharField(max_length=128), blank=True, null=True)
    title = models.CharField(max_length=256)
    description = models.CharField(max_length=1024, blank=True, null=True)
    url = models.URLField(max_length=1024)
    publish_date = models.DateTimeField()
    publisher = models.CharField(max_length=128)


class OSMDaily(TimeStampedModel):
    symbol = models.CharField(max_length=64, db_index=True)
    date = models.DateField()
    timestamp = models.IntegerField()
    open = models.DecimalField(max_digits=32, decimal_places=18)
    close = models.DecimalField(max_digits=32, decimal_places=18)
    drawdown = models.DecimalField(max_digits=6, decimal_places=2)
    daily_low = models.DecimalField(max_digits=32, decimal_places=18)
    daily_high = models.DecimalField(max_digits=32, decimal_places=18)
    greatest_drop = models.DecimalField(max_digits=6, decimal_places=2)
    drop_start = models.DecimalField(max_digits=32, decimal_places=18)
    drop_end = models.DecimalField(max_digits=32, decimal_places=18)

    class Meta:
        unique_together = ["symbol", "date"]
        get_latest_by = "timestamp"
        ordering = ["-timestamp"]


# TODO: remove this comment - below are models from API app


class Asset(TimeStampedModel):
    address = models.CharField(max_length=42, null=True)
    name = models.CharField(max_length=64, null=True)
    symbol = models.CharField(max_length=64, unique=True)
    type = models.CharField(max_length=32, choices=ASSET_TYPES)
    decimals = models.IntegerField(null=True)
    underlying_symbol = models.CharField(max_length=64, null=True)
    price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    total_supply = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    market_cap = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    class Meta:
        get_latest_by = "created"
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol

    def __repr__(self):
        return f"<{self.__class__.__name__}: name={self.symbol}>"


class SlippageDaily(UUIDModel, TimeStampedModel):
    timestamp = models.IntegerField()
    date = models.DateField()
    source = models.CharField(max_length=32)
    usd_amount = models.BigIntegerField()

    slippage_list = ArrayField(
        models.DecimalField(decimal_places=4, max_digits=8),
        blank=True,
        null=True,
        default=list,
    )
    slippage_percent_avg = models.DecimalField(
        decimal_places=4, max_digits=8, null=True
    )

    pair = models.ForeignKey(
        "SlippagePair", related_name="slippages", on_delete=models.CASCADE
    )
    is_active = models.BooleanField(default=False)

    class Meta:
        get_latest_by = "date"


class SlippagePair(TimeStampedModel):
    from_asset = models.ForeignKey(
        "Asset", related_name="slippage_pair_from", on_delete=models.CASCADE
    )
    to_asset = models.ForeignKey(
        "Asset", related_name="slippage_pair_to", on_delete=models.CASCADE
    )
    interval = models.IntegerField()
    last_run = models.DateTimeField(null=True, blank=True)

    class Meta:
        get_latest_by = "created"


class TokenPriceHistory(TimeStampedModel):
    underlying_symbol = models.CharField(max_length=16, db_index=True)
    price = models.DecimalField(max_digits=32, decimal_places=18)
    timestamp = models.BigIntegerField(db_index=True)
    round_id = models.CharField(max_length=42)
    underlying_address = models.CharField(max_length=42)

    class Meta:
        get_latest_by = "timestamp"
        ordering = ["-timestamp"]
        unique_together = ["underlying_address", "round_id", "timestamp"]


class OHLCVPair(TimeStampedModel):
    from_asset_symbol = models.CharField(max_length=16, db_index=True)
    to_asset_symbol = models.CharField(max_length=16, db_index=True)
    exchange = models.CharField(max_length=128)
    ohlcv_type = models.CharField(
        max_length=16, choices=OHLCV_TYPES, default=OHLCV_TYPE_DAILY
    )
    to_asset_is_stable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    class Meta:
        get_latest_by = "modified"
        ordering = ["-modified"]
        unique_together = [
            "from_asset_symbol",
            "to_asset_symbol",
            "exchange",
            "ohlcv_type",
        ]

    def __str__(self):
        return f"{self.from_asset_symbol}-{self.to_asset_symbol} ({self.exchange})"

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}: from_asset={self.from_asset_symbol}, "
            f"to_asset={self.to_asset_symbol}, "
            f"exchange={self.exchange}, is_active={self.is_active}>"
        )


class OHLCV(TimeStampedModel):
    pair = models.ForeignKey(
        "OHLCVPair", related_name="history", on_delete=models.CASCADE
    )
    ohlcv_type = models.CharField(max_length=16, choices=OHLCV_TYPES)
    timestamp = models.IntegerField(db_index=True)
    datetime = models.DateTimeField(db_index=True)
    close = models.DecimalField(max_digits=32, decimal_places=18)
    high = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    low = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    open = models.DecimalField(max_digits=32, decimal_places=18)
    volume_from = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    volume_to = models.DecimalField(max_digits=32, decimal_places=18)
    volume_usd = models.DecimalField(max_digits=32, decimal_places=18)
    drawdown = models.DecimalField(max_digits=10, decimal_places=3, null=True)
    drawdown_hl = models.DecimalField(max_digits=10, decimal_places=3, null=True)

    class Meta:
        unique_together = ["pair", "ohlcv_type", "timestamp"]
        get_latest_by = "timestamp"
        ordering = ["-timestamp"]


class Volatility(TimeStampedModel):
    pair = models.ForeignKey(
        "OHLCVPair", related_name="volatility", on_delete=models.CASCADE
    )
    date = models.DateField()
    volatility = models.DecimalField(max_digits=8, decimal_places=3)

    class Meta:
        unique_together = ["pair", "date"]
        get_latest_by = "date"


class Pool(TimeStampedModel):
    contract_address = models.CharField(max_length=42)
    from_asset_symbol = models.CharField(max_length=16)
    to_asset_symbol = models.CharField(max_length=16)
    exchange = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)

    class Meta:
        get_latest_by = "created"
        unique_together = [
            "contract_address",
            "from_asset_symbol",
            "to_asset_symbol",
            "exchange",
        ]

    def __str__(self):
        return f"{self.from_asset_symbol}-{self.to_asset_symbol} ({self.exchange})"

    def __repr__(self):
        return (
            f"<{self.__class__.__name__}: from_asset={self.from_asset_symbol}, "
            f"to_asset={self.to_asset_symbol}, "
            f"exchange={self.exchange}, contract_address={self.contract_address}>"
        )


class PoolInfo(TimeStampedModel):
    pool = models.ForeignKey("Pool", related_name="infos", on_delete=models.CASCADE)
    total_supply = models.DecimalField(decimal_places=6, max_digits=32, null=True)
    reserve_usd = models.DecimalField(decimal_places=6, max_digits=32, null=True)
    volume_usd = models.DecimalField(decimal_places=6, max_digits=32, null=True)
    tx_count = models.IntegerField(null=True)
    timestamp = models.IntegerField()
    datetime = models.DateTimeField()

    class Meta:
        get_latest_by = "timestamp"
        unique_together = ["pool", "timestamp"]

    def __repr__(self):
        return f"<{self.__class__.__name__}: pool={self.pool}>"


class MarketPrice(models.Model):
    symbol = models.CharField(max_length=32, db_index=True)
    price = models.DecimalField(max_digits=32, decimal_places=18)
    timestamp = models.IntegerField()
    datetime = models.DateTimeField()

    class Meta:
        get_latest_by = "timestamp"
        ordering = ("timestamp",)
        unique_together = ["symbol", "timestamp"]


class Block(models.Model):
    block_number = models.IntegerField(db_index=True, unique=True)
    timestamp = models.IntegerField()
    datetime = models.DateTimeField(null=True)

    class Meta:
        get_latest_by = "block_number"
        ordering = ("block_number",)


class Liquidation(TimeStampedModel):
    block_number = models.BigIntegerField(db_index=True)
    timestamp = models.BigIntegerField(null=True)
    datetime = models.DateTimeField(null=True)
    tx_hash = models.CharField(max_length=128)
    debt_symbol = models.CharField(max_length=32)
    debt_token_price = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    debt_repaid = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    collateral_symbol = models.CharField(max_length=32)
    collateral_token_price = models.DecimalField(
        max_digits=32, decimal_places=18, null=True
    )
    collateral_seized = models.DecimalField(max_digits=32, decimal_places=18, null=True)
    protocol = models.CharField(max_length=64)
    ilk = models.CharField(max_length=64, null=True)
    finished = models.BooleanField(default=True)
    uid = models.IntegerField(null=True)
    penalty = models.DecimalField(max_digits=32, decimal_places=18, null=True)

    class Meta:
        unique_together = ["tx_hash", "uid"]
        get_latest_by = "block_number"
        ordering = ("block_number",)


class DEFILocked(TimeStampedModel):
    protocol = models.CharField(max_length=64)
    underlying_symbol = models.CharField(max_length=64)
    date = models.DateField()
    datetime = models.DateTimeField()
    timestamp = models.IntegerField()
    balance = models.DecimalField(max_digits=32, decimal_places=18)

    class Meta:
        get_latest_by = "timestamp"
