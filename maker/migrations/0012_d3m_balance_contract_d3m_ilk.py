# Generated by Django 4.0.8 on 2023-01-18 11:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0011_slippagepair_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='d3m',
            name='balance_contract',
            field=models.CharField(max_length=42, null=True),
        ),
        migrations.AddField(
            model_name='d3m',
            name='ilk',
            field=models.CharField(max_length=32, null=True),
        ),
    ]
