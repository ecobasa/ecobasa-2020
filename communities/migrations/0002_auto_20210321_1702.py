# Generated by Django 3.1.7 on 2021-03-21 16:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='community',
            name='slug',
            field=models.SlugField(blank=True, unique=True, verbose_name='Slug'),
        ),
    ]