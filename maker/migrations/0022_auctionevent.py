# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 4.0.8 on 2023-10-25 13:45

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0021_auctionv1_clipperevent_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuctionEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('order_index', models.CharField(max_length=26, unique=True)),
                ('auction_uid', models.IntegerField(null=True)),
                ('ilk', models.CharField(max_length=32)),
                ('datetime', models.DateTimeField(null=True)),
                ('debt', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('available_collateral', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('sold_collateral', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('recovered_debt', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('type', models.CharField(max_length=16)),
                ('collateral_price', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('init_price', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('osm_price', models.DecimalField(decimal_places=18, max_digits=32)),
                ('mkt_price', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('keeper', models.CharField(max_length=64, null=True)),
                ('incentives', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('caller', models.CharField(max_length=64, null=True)),
                ('tx_hash', models.CharField(max_length=128, null=True)),
                ('urn', models.CharField(max_length=42, null=True)),
                ('block_number', models.BigIntegerField(null=True)),
                ('auction', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='maker.auctionv1')),
            ],
            options={
                'ordering': ['order_index'],
                'get_latest_by': 'order_index',
            },
        ),
    ]
