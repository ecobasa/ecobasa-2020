from django.contrib.gis import admin
from .models import Listing, ListingCategory


@admin.register(Listing)
class ListingAdmin(admin.OSMGeoAdmin):
    list_display = (
        "title",
        "type",
    )
    search_fields = ("title",)
    ordering = ("title",)
    list_filter = ("type",)


@admin.register(ListingCategory)
class ListingCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    ordering = (
        "order",
        "name",
    )
