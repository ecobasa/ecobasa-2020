from django.contrib import admin

from .models import Attendee, Brought, Entry, Giftsheet, GiftsheetPhoto, Guest, Idea, Invitation, Scribe


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "event", "people", "confirmed_at", "user")
    list_filter = ("confirmed_at",)
    search_fields = ("name", "email", "event__title")
    raw_id_fields = ("event", "user", "added_by")
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


@admin.register(Brought)
class BroughtAdmin(admin.ModelAdmin):
    list_display = ("listing", "event", "created_at")
    search_fields = ("listing__title", "event__title")
    raw_id_fields = ("event", "listing")


@admin.register(Giftsheet)
class GiftsheetAdmin(admin.ModelAdmin):
    list_display = ("event", "created_at", "closed_at", "closed_by")
    search_fields = ("event__title",)
    raw_id_fields = ("event", "closed_by")


class IdeaInline(admin.TabularInline):
    model = Idea
    extra = 0
    raw_id_fields = ("from_user", "from_guest", "created_by")


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    inlines = [IdeaInline]
    list_display = ("text", "type", "event", "state", "created_at")
    list_filter = ("type", "state")
    search_fields = ("text", "event__title")
    raw_id_fields = ("event", "from_user", "from_guest", "for_user", "for_guest", "listing", "match", "created_by")


@admin.register(Scribe)
class ScribeAdmin(admin.ModelAdmin):
    list_display = ("user", "event")
    search_fields = ("user__name", "user__email", "event__title")
    raw_id_fields = ("event", "user")


@admin.register(GiftsheetPhoto)
class GiftsheetPhotoAdmin(admin.ModelAdmin):
    list_display = ("event", "created_at")
    search_fields = ("event__title",)
    raw_id_fields = ("event",)
