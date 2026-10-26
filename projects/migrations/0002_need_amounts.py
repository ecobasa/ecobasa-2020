import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Needs get a quantity with a unit (the old free-text amount becomes details) and an
    optional gift category; offers say how much they bring. The offers table stays, it
    only gets a model (NeedOffer) and a quantity column."""

    dependencies = [
        ("gifts", "0014_alter_adcategory_id"),
        ("matches", "0002_matchmessage_counter_stay"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(model_name="need", old_name="amount", new_name="details"),
        migrations.AlterField(
            model_name="need", name="details",
            field=models.CharField(blank=True, max_length=100, verbose_name="Details"),
        ),
        migrations.AddField(
            model_name="need", name="quantity",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="How many / how much?"),
        ),
        migrations.AddField(
            model_name="need", name="unit",
            field=models.CharField(
                blank=True, max_length=10, verbose_name="Unit",
                choices=[
                    ("people", "people"), ("pieces", "pieces"), ("kg", "kg"), ("m", "m"),
                    ("m2", "m²"), ("m3", "m³"), ("l", "litres"), ("days", "days"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="need", name="category",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_needs", to="gifts.listingcategory", verbose_name="Gift category",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="NeedOffer",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("need", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="need_offers", to="projects.need")),
                        ("match", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="need_offers", to="matches.match")),
                    ],
                    options={"db_table": "projects_need_offers", "unique_together": {("need", "match")}},
                ),
                migrations.AlterField(
                    model_name="need", name="offers",
                    field=models.ManyToManyField(blank=True, related_name="needs", through="projects.NeedOffer", to="matches.match"),
                ),
            ],
        ),
        migrations.AddField(
            model_name="needoffer", name="quantity",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
