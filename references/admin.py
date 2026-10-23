from django.contrib import admin
from .models import Reference


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ("author", "recipient", "content_type", "subject", "impression", "created_at")
    list_filter = ("impression", "content_type")
    search_fields = ("author__email", "recipient__email", "text")
    readonly_fields = ("created_at", "updated_at")
