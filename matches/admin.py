from django.contrib import admin
from .models import Contribution, Match, MatchMessage, Suggestion, VolunteerDetails


class MatchMessageInline(admin.TabularInline):
    model = MatchMessage
    extra = 0
    readonly_fields = ("sender", "body", "status_to", "created_at")


class ContributionInline(admin.TabularInline):
    model = Contribution
    extra = 0
    raw_id_fields = ("listing",)


class VolunteerDetailsInline(admin.StackedInline):
    model = VolunteerDetails
    extra = 0


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("from_user", "recipient", "content_type", "target", "status", "created_at")
    list_filter  = ("status", "content_type")
    search_fields = ("from_user__email", "recipient__email")
    readonly_fields = ("created_at", "responded_at")
    inlines = [ContributionInline, VolunteerDetailsInline, MatchMessageInline]


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ("user", "own_type", "other_type", "other_user", "reason", "distance_km", "created_at", "seen_at", "emailed_at", "dismissed_at")
    list_filter = ("reason", "other_type")
    raw_id_fields = ("user", "other_user")
