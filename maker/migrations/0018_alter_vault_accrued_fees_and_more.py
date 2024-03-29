# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 4.0.8 on 2023-10-12 12:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0017_walletexternalprotocol'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vault',
            name='accrued_fees',
            field=models.DecimalField(decimal_places=18, max_digits=32, null=True),
        ),
        migrations.AlterField(
            model_name='vault',
            name='available_collateral',
            field=models.DecimalField(decimal_places=18, max_digits=32, null=True),
        ),
        migrations.AlterField(
            model_name='vault',
            name='available_debt',
            field=models.DecimalField(decimal_places=18, max_digits=32, null=True),
        ),
        migrations.AlterField(
            model_name='vault',
            name='block_created',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='vault',
            name='paid_fees',
            field=models.DecimalField(decimal_places=18, max_digits=32, null=True),
        ),
        migrations.AlterField(
            model_name='vault',
            name='principal',
            field=models.DecimalField(decimal_places=18, max_digits=32, null=True),
        ),
    ]
