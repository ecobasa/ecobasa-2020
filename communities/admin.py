from django.contrib.gis import admin
from .models import Community, CommunityPhoto


class CommunityPhotoInline(admin.TabularInline):
    model = CommunityPhoto
    extra = 1
    fields = ("image",)


@admin.register(Community)
class CommunityAdmin(admin.GeoModelAdmin):
    list_display = (
        "name",
        "owner",
    )
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields=('slug',)
    inlines = [CommunityPhotoInline]