from django.db import migrations

# A listing's kind already says whether it is a material or a tool
KIND_CATEGORIES = ["Tools & Equipment", "Building Materials"]


def remove_kind_categories(apps, schema_editor):
    ListingCategory = apps.get_model("gifts", "ListingCategory")
    ListingCategory.objects.filter(name__in=KIND_CATEGORIES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0016_load_curated_skills"),
    ]

    operations = [
        migrations.RunPython(remove_kind_categories, migrations.RunPython.noop),
    ]
