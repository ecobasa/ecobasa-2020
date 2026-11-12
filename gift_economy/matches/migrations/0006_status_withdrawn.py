from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0005_staydetails_people"),
    ]

    operations = [
        migrations.AlterField(
            model_name="match",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                    ("declined", "Declined"),
                    ("counter", "Counter-proposed"),
                    ("withdrawn", "Withdrawn"),
                ],
                default="pending",
                max_length=20,
                verbose_name="Status",
            ),
        ),
        migrations.AlterField(
            model_name="matchmessage",
            name="status_to",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                    ("declined", "Declined"),
                    ("counter", "Counter-proposed"),
                    ("withdrawn", "Withdrawn"),
                ],
                max_length=20,
                verbose_name="Decision",
            ),
        ),
    ]
