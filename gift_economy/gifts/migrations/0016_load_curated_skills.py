from django.db import migrations


def load_skills(apps, schema_editor):
    from gift_economy.gifts.management.commands.load_curated_skills import SKILLS
    SkillTaxonomy = apps.get_model("gifts", "SkillTaxonomy")
    for slug, en, de, es, fr in SKILLS:
        SkillTaxonomy.objects.update_or_create(
            slug=slug,
            defaults={"names": {"en": en, "de": de, "es": es, "fr": fr}},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0015_listing_for_everything"),
    ]

    operations = [
        migrations.RunPython(load_skills, migrations.RunPython.noop),
    ]
