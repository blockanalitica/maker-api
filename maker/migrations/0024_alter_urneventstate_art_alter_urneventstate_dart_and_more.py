# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 4.1.7 on 2024-08-01 07:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maker", "0023_slippagedaily_slippage_percent_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="urneventstate",
            name="art",
            field=models.DecimalField(decimal_places=0, max_digits=128),
        ),
        migrations.AlterField(
            model_name="urneventstate",
            name="dart",
            field=models.DecimalField(decimal_places=0, max_digits=128),
        ),
        migrations.AlterField(
            model_name="urneventstate",
            name="debt",
            field=models.DecimalField(decimal_places=18, max_digits=64),
        ),
        migrations.AlterField(
            model_name="urneventstate",
            name="dink",
            field=models.DecimalField(decimal_places=0, max_digits=128),
        ),
        migrations.AlterField(
            model_name="urneventstate",
            name="ink",
            field=models.DecimalField(decimal_places=0, default=0, max_digits=128),
        ),
        migrations.AlterField(
            model_name="urneventstate",
            name="rate",
            field=models.DecimalField(decimal_places=0, default=0, max_digits=128),
        ),
    ]
