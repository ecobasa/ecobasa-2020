# Generated by Django 3.0.8 on 2020-07-16 13:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_auto_20200713_2333'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='username',
            field=models.CharField(blank=True, default='', max_length=150, unique=True, verbose_name='username'),
            preserve_default=False,
        ),
    ]
