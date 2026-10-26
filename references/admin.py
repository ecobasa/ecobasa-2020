from django.contrib import admin
from .models import Reference, ReferenceRequest


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("author", "recipient", "content_type", "subject", "impression", "share_publicly", "featured_at", "created_at")
    list_filter = ("impression", "content_type", "share_publicly")
    search_fields = ("author__email", "recipient__email", "text")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ReferenceRequest)
class ReferenceRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "match", "sent_at", "reference")
    raw_id_fields = ("match", "user", "reference")
    readonly_fields = ("key", "sent_at")
