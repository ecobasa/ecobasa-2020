from django.contrib import admin

from .models import Attendee, Guest, Invitation


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


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "name", "email", "invited_by", "created_at")
    search_fields = ("name", "email", "user__name", "event__title")
    raw_id_fields = ("event", "user", "invited_by")
    readonly_fields = ("token", "created_at")
