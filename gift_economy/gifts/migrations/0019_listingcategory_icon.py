from django.db import migrations, models


def load_icons(apps, schema_editor):
    from gift_economy.gifts.management.commands.load_listing_categories import load_categories
    load_categories(apps.get_model("gifts", "ListingCategory"))


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0018_themed_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="listingcategory",
            name="icon",
            field=models.CharField(default="fa-gift", max_length=40, verbose_name="Icon"),
        ),
        migrations.RunPython(load_icons, migrations.RunPython.noop),
    ]
