from django.contrib.gis import admin
from .models import FoodThing, Listing, ListingCategory, MaterialThing, OtherThing, SeedPlantThing, ToolThing, VehicleThing
from .skills.models import Skill


@admin.register(Listing)
class ListingAdmin(admin.GISModelAdmin):
    list_display = ("title", "type", "kind", "thing", "owner", "community", "project")
    search_fields = ("title", "skill__name", "owner__name", "community__name")
    ordering = ("title",)
    list_filter = ("type", "kind")
    raw_id_fields = ("owner", "community", "project", "skill")
    # Recognized from the title on every save
    readonly_fields = ("thing",)


@admin.register(ListingCategory)
class ListingCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "theme", "slug", "order")
    list_filter = ("theme",)
    ordering = (
        "order",
        "name",
    )

class SkillListingInline(admin.TabularInline):
    """Who offers or wishes for the skill."""
    model = Listing
    fk_name = "skill"
    extra = 0
    fields = ("type", "kind", "owner", "community", "project", "level", "available")
    raw_id_fields = ("owner", "community", "project")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ("name", "slug", "offer_count", "wish_count")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [SkillListingInline]

    @admin.display(description="Offers")
    def offer_count(self, obj):
        return obj.listings.filter(type=Listing.TYPE_OFFER).count()

    @admin.display(description="Wishes")
    def wish_count(self, obj):
        return obj.listings.filter(type=Listing.TYPE_WISH).count()


class VocabularyAdmin(admin.ModelAdmin):
    """One vocabulary of things (gifts/vocabularies/); edit names and broader things here,
    and run load_vocabularies to recognize them in existing listings again."""
    list_display = ("__str__", "slug", "parent", "category", "listing_count")
    list_filter = ("category",)
    search_fields = ("slug", "names", "other_names")
    raw_id_fields = ("parent",)
    exclude = ("kind",)

    @admin.display(description="Listings")
    def listing_count(self, obj):
        return obj.listings.count()


for vocabulary in (ToolThing, MaterialThing, VehicleThing, SeedPlantThing, FoodThing, OtherThing):
    admin.site.register(vocabulary, VocabularyAdmin)
