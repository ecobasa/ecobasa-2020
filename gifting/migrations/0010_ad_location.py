# Generated by Django 3.0.8 on 2020-07-23 10:54

import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('gifting', '0009_auto_20200716_1849'),
    ]

    operations = [
        migrations.AddField(
            model_name='ad',
            name='location',
            field=django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326, verbose_name='Location'),
        ),
    ]
