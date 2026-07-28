from django.contrib import admin
from .models import Match, MatchMessage, VolunteerDetails


class MatchMessageInline(admin.TabularInline):
    model = MatchMessage
    extra = 0
    readonly_fields = ("sender", "body", "status_to", "created_at")


class VolunteerDetailsInline(admin.StackedInline):
    model = VolunteerDetails
    extra = 0


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("from_user", "recipient", "content_type", "target", "status", "created_at")
    list_filter  = ("status", "content_type")
    search_fields = ("from_user__email", "recipient__email")
    readonly_fields = ("created_at", "responded_at")
    inlines = [VolunteerDetailsInline, MatchMessageInline]
