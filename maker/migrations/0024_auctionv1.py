# Generated by Django 4.0.8 on 2023-10-25 11:24

from django.db import migrations, models
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0023_clipperevent_penalty'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuctionV1',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('ilk', models.CharField(db_index=True, max_length=32)),
                ('symbol', models.CharField(max_length=32, null=True)),
                ('auction_id', models.IntegerField()),
                ('auction_start', models.DateTimeField(null=True)),
                ('vault', models.CharField(max_length=32, null=True)),
                ('urn', models.CharField(max_length=64, null=True)),
                ('debt', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('debt_liquidated', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('available_collateral', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('kicked_collateral', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('penalty', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('penalty_fee', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('sold_collateral', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('recovered_debt', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('auction_end', models.DateTimeField(null=True)),
                ('finished', models.IntegerField(null=True)),
                ('duration', models.IntegerField(null=True)),
                ('avg_price', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('osm_settled_avg', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
                ('mkt_settled_avg', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
