from django.db import migrations


def load_and_recognize(apps, schema_editor):
    """Loads the vocabularies again, now with tropical and subtropical crops, green
    manure, Asian vegetables and perennial vegetables, and recognizes listings again."""
    from gift_economy.gifts.management.commands.load_vocabularies import load_vocabularies
    from gift_economy.gifts.things import recognize_all
    Thing = apps.get_model("gifts", "Thing")
    load_vocabularies(Thing, apps.get_model("gifts", "ListingCategory"))
    recognize_all(apps.get_model("gifts", "Listing"), Thing)


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0011_merge_20261030_1142"),
    ]

    operations = [
        migrations.RunPython(load_and_recognize, migrations.RunPython.noop),
    ]
