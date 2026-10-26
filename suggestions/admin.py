from django.contrib import admin

from .models import Suggestion


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ("user", "own_type", "other_type", "other_user", "reason", "distance_km", "created_at", "seen_at", "emailed_at", "dismissed_at")
    list_filter = ("reason", "other_type")
    raw_id_fields = ("user", "other_user")
