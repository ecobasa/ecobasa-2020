from django.contrib import admin

from gift_economy.gifts.models import Listing
from .models import Project


class ListingInline(admin.TabularInline):
    """Its needs (wishes) and the skills you can learn in it (offers)."""
    model = Listing
    fk_name = "project"
    extra = 0
    fields = ("type", "kind", "title", "skill", "quantity", "unit", "description", "covered_at", "order")
    raw_id_fields = ("skill",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "community", "starts_on", "ends_on", "updated_at", "archived_at")
    list_filter = ("archived_at",)
    search_fields = ("title", "description", "community__name")
    raw_id_fields = ("community", "created_by")
    readonly_fields = ("created_at",)
    inlines = [ListingInline]
