# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 4.0.8 on 2023-01-17 14:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0010_alter_ilk_fee_in_alter_ilk_fee_out'),
    ]

    operations = [
        migrations.AddField(
            model_name='slippagepair',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
