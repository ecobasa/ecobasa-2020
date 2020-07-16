# Generated by Django 3.0.8 on 2020-07-16 13:33

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gifting', '0005_auto_20200714_2025'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='ad',
            options={'ordering': ['-created_at'], 'verbose_name': 'Ad', 'verbose_name_plural': 'Ads'},
        ),
        migrations.AddField(
            model_name='ad',
            name='owner',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ads', to=settings.AUTH_USER_MODEL, verbose_name='Owner'),
        ),
        migrations.AlterField(
            model_name='ad',
            name='type',
            field=models.CharField(choices=[('offer', 'Offer'), ('wish', 'Wish')], default='offer', max_length=5, verbose_name='Type'),
        ),
    ]