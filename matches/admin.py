from django.contrib import admin
from .models import VolunteerRequest, VolunteerRequestMessage


class MessageInline(admin.TabularInline):
    model = VolunteerRequestMessage
    extra = 0
    readonly_fields = ("sender", "body", "created_at")


@admin.register(VolunteerRequest)
class VolunteerRequestAdmin(admin.ModelAdmin):
    list_display = ("from_user", "community", "status", "volunteer_mode", "stay_from", "stay_to", "created_at")
    list_filter  = ("status", "volunteer_mode")
    search_fields = ("from_user__email", "community__name")
    readonly_fields = ("created_at", "responded_at")
    inlines = [MessageInline]
