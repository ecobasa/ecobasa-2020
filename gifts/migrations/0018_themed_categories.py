from django.db import migrations, models
from django.utils.text import slugify

# Categories from before the themes, by name; their listings keep them
OLD_SLUGS = {
    "Garden & Farm": "garden-farm",
    "Food & Preserves": "food-preserves",
    "Books & Learning": "books-learning",
    "Household & Furniture": "kitchen-household",
}


def load_themed_categories(apps, schema_editor):
    from gifts.management.commands.load_listing_categories import load_categories
    ListingCategory = apps.get_model("gifts", "ListingCategory")
    taken = set()
    for category in ListingCategory.objects.all():
        slug = OLD_SLUGS.get(category.name) or slugify(category.name)[:45] or "category"
        while slug in taken:
            slug += "-"
        taken.add(slug)
        category.slug = slug
        category.save(update_fields=["slug"])
    load_categories(ListingCategory)


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0017_remove_kind_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="listingcategory",
            name="slug",
            field=models.SlugField(db_index=False, max_length=50, null=True, verbose_name="Slug"),
        ),
        migrations.AddField(
            model_name="listingcategory",
            name="names",
            field=models.JSONField(blank=True, default=dict, verbose_name="Names"),
        ),
        migrations.AddField(
            model_name="listingcategory",
            name="theme",
            field=models.CharField(
                choices=[("land", "Land & Food"), ("building", "Building & Energy"), ("home", "Home & Living"),
                         ("move", "On the Move"), ("culture", "Culture & Learning")],
                default="home", max_length=20, verbose_name="Theme",
            ),
        ),
        migrations.RunPython(load_themed_categories, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="listingcategory",
            name="slug",
            field=models.SlugField(max_length=50, unique=True, verbose_name="Slug"),
        ),
    ]
