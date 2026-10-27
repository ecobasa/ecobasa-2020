from django.db import migrations, models


def move_listings(apps, schema_editor):
    """What volunteers bring along moves from their details to the match."""
    VolunteerDetails = apps.get_model("matches", "VolunteerDetails")
    for details in VolunteerDetails.objects.prefetch_related("bring_listings"):
        details.match.listings.add(*details.bring_listings.all())


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0016_listing_kind"),
        ("matches", "0005_volunteerdetails_bring_listings"),
    ]

    operations = [
        migrations.AddField(
            model_name="match",
            name="listings",
            field=models.ManyToManyField(
                blank=True,
                related_name="extra_matches",
                to="gifts.listing",
                verbose_name="Also part of this exchange",
            ),
        ),
        migrations.RunPython(move_listings, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="volunteerdetails",
            name="bring_listings",
        ),
    ]
