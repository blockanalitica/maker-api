# SPDX-FileCopyrightText: © 2022 Dai Foundation <www.daifoundation.org>
#
# SPDX-License-Identifier: Apache-2.0

# Generated by Django 4.0.8 on 2022-10-28 10:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0009_psmdaisupply'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ilk',
            name='fee_in',
            field=models.DecimalField(decimal_places=4, max_digits=8, null=True),
        ),
        migrations.AlterField(
            model_name='ilk',
            name='fee_out',
            field=models.DecimalField(decimal_places=4, max_digits=8, null=True),
        ),
    ]
