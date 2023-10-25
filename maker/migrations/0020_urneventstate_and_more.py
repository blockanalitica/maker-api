# Generated by Django 4.1.7 on 2023-10-24 13:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('maker', '0019_alter_vault_unique_together_alter_vault_uid_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UrnEventState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('block_number', models.IntegerField()),
                ('datetime', models.DateTimeField()),
                ('tx_hash', models.CharField(max_length=66)),
                ('order_index', models.CharField(max_length=26)),
                ('ilk', models.CharField(max_length=64)),
                ('urn', models.CharField(max_length=42)),
                ('operation', models.CharField(max_length=64)),
                ('event', models.CharField(max_length=64)),
                ('ink', models.DecimalField(decimal_places=0, default=0, max_digits=48)),
                ('art', models.DecimalField(decimal_places=0, max_digits=48)),
                ('dart', models.DecimalField(decimal_places=0, max_digits=48)),
                ('dink', models.DecimalField(decimal_places=0, max_digits=48)),
                ('rate', models.DecimalField(decimal_places=0, default=0, max_digits=48)),
                ('debt', models.DecimalField(decimal_places=18, max_digits=32)),
                ('collateral_price', models.DecimalField(decimal_places=18, max_digits=32, null=True)),
            ],
            options={
                'ordering': ['order_index'],
                'get_latest_by': 'order_index',
            },
        ),
        migrations.AddIndex(
            model_name='urneventstate',
            index=models.Index(fields=['ilk', 'urn'], name='maker_urnev_ilk_dc3b94_idx'),
        ),
        migrations.AddIndex(
            model_name='urneventstate',
            index=models.Index(fields=['block_number'], name='maker_urnev_block_n_435d42_idx'),
        ),
        migrations.AddIndex(
            model_name='urneventstate',
            index=models.Index(fields=['ilk'], name='maker_urnev_ilk_c03aa9_idx'),
        ),
        migrations.AddIndex(
            model_name='urneventstate',
            index=models.Index(fields=['urn'], name='maker_urnev_urn_4aff56_idx'),
        ),
        migrations.AddIndex(
            model_name='urneventstate',
            index=models.Index(fields=['order_index'], name='maker_urnev_order_i_7802fc_idx'),
        ),
        migrations.AddIndex(
            model_name='urneventstate',
            index=models.Index(fields=['urn', 'ilk', 'order_index'], name='maker_urnev_urn_4d4dd8_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='urneventstate',
            unique_together={('urn', 'ilk', 'order_index')},
        ),
    ]
