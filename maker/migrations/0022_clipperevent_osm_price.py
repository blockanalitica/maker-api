# Generated by Django 4.0.8 on 2023-10-25 10:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0021_clipperevent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='clipperevent',
            name='osm_price',
            field=models.DecimalField(decimal_places=18, max_digits=32, null=True),
        ),
    ]
