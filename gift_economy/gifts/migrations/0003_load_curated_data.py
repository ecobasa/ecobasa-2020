from django.db import migrations


def load_curated_data(apps, schema_editor):
    from gift_economy.gifts.management.commands.load_curated_skills import SKILLS
    from gift_economy.gifts.management.commands.load_listing_categories import load_categories
    SkillTaxonomy = apps.get_model("gifts", "SkillTaxonomy")
    for slug, en, de, es, fr in SKILLS:
        SkillTaxonomy.objects.update_or_create(
            slug=slug,
            defaults={"names": {"en": en, "de": de, "es": es, "fr": fr}},
        )
    load_categories(apps.get_model("gifts", "ListingCategory"))


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(load_curated_data, migrations.RunPython.noop),
    ]
