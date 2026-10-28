from django.contrib.gis import admin
from .models import Listing, ListingCategory
from .skills.models import Skill


@admin.register(Listing)
class ListingAdmin(admin.GISModelAdmin):
    list_display = ("title", "type", "kind", "owner", "community", "project")
    search_fields = ("title", "skill__name", "owner__name", "community__name")
    ordering = ("title",)
    list_filter = ("type", "kind")
    raw_id_fields = ("owner", "community", "project", "skill")


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
