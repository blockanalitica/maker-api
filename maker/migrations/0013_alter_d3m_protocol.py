# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 4.0.8 on 2023-01-18 11:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maker", "0012_d3m_balance_contract_d3m_ilk"),
    ]

    operations = [
        migrations.AlterField(
            model_name="d3m",
            name="protocol",
            field=models.CharField(max_length=32, null=True),
        ),
    ]