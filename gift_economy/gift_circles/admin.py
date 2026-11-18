from django.contrib import admin

from .models import Attendee, Guest


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "event", "people", "confirmed_at", "user")
    list_filter = ("confirmed_at",)
    search_fields = ("name", "email", "event__title")
    raw_id_fields = ("event", "user")
    readonly_fields = ("token", "created_at", "mailed_at")


@admin.register(Attendee)
class AttendeeAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "keep_on_ecobasa")
    search_fields = ("user__name", "user__email", "event__title")
    raw_id_fields = ("event", "user")
