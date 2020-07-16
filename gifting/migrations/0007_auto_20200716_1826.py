# Generated by Django 3.0.8 on 2020-07-16 16:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gifting', '0006_auto_20200716_1533'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, verbose_name='Name')),
            ],
            options={
                'verbose_name': 'Ad Category',
                'verbose_name_plural': 'Ad Categories',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='ad',
            name='categories',
            field=models.ManyToManyField(related_name='ads', to='gifting.AdCategory', verbose_name='Categories'),
        ),
    ]