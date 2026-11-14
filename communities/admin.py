from django.contrib.gis import admin
from .models import Community, CommunityPhoto, Membership


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ("user", "match", "created_at", "ended_at")
    readonly_fields = ("match", "created_at")
    raw_id_fields = ("user",)


class CommunityPhotoInline(admin.TabularInline):
    model = CommunityPhoto
    extra = 1
    fields = ("image",)


@admin.register(Community)
class CommunityAdmin(admin.GISModelAdmin):
    list_display = (
        "name",
        "ambassador",
    )
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields=('slug',)
    inlines = [MembershipInline, CommunityPhotoInline]