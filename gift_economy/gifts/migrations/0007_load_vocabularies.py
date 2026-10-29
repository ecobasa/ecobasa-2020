from django.db import migrations


def load_and_recognize(apps, schema_editor):
    from gift_economy.gifts.management.commands.load_vocabularies import load_vocabularies
    from gift_economy.gifts.things import recognize_all
    Thing = apps.get_model("gifts", "Thing")
    load_vocabularies(Thing, apps.get_model("gifts", "ListingCategory"))
    recognize_all(apps.get_model("gifts", "Listing"), Thing)


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0006_thing"),
    ]

    operations = [
        migrations.RunPython(load_and_recognize, migrations.RunPython.noop),
    ]
