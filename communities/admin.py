from django.contrib.gis import admin
from .models import Community


@admin.register(Community)
class CommunityAdmin(admin.GeoModelAdmin):
    list_display = (
        "name",
        "owner",
    )
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields=('slug',)