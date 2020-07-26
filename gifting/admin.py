from django.contrib.gis import admin
from .models import Ad, AdCategory


@admin.register(Ad)
class AdAdmin(admin.GeoModelAdmin):
    list_display = (
        "title",
        "type",
    )
    search_fields = ("title",)
    ordering = ("title",)
    list_filter = ("type",)


@admin.register(AdCategory)
class AdCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    ordering = (
        "order",
        "name",
    )
