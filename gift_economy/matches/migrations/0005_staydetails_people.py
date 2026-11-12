from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0004_suggestion_reason_thing"),
    ]

    operations = [
        migrations.AddField(
            model_name="staydetails",
            name="people",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="People coming"),
        ),
    ]
