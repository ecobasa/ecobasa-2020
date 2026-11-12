from django.contrib import admin

from gift_economy.gifts.models import Listing
from .models import Event


class ListingInline(admin.TabularInline):
    """Its needs (wishes) and the skills you can learn in it (offers)."""
    model = Listing
    fk_name = "event"
    extra = 0
    fields = ("type", "kind", "title", "skill", "quantity", "unit", "description", "covered_at", "order")
    raw_id_fields = ("skill",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "community", "starts_on", "ends_on", "is_open", "updated_at", "archived_at")
    list_filter = ("kind", "is_open", "archived_at")
    search_fields = ("title", "description", "community__name")
    raw_id_fields = ("community", "created_by")
    readonly_fields = ("slug", "created_at")
    inlines = [ListingInline]
