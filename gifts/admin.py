from django.contrib.gis import admin
from .models import Listing, ListingCategory


@admin.register(Listing)
class ListingAdmin(admin.OSMGeoAdmin):
    list_display = ("title", "type", "kind", "owner", "community", "project")
    search_fields = ("title", "skill__name", "owner__name", "community__name")
    ordering = ("title",)
    list_filter = ("type", "kind")
    raw_id_fields = ("owner", "community", "project", "skill")


@admin.register(ListingCategory)
class ListingCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    ordering = (
        "order",
        "name",
    )
