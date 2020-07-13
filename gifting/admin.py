from django.contrib import admin
from .models import Ad


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "type",
    )
    search_fields = ("title",)
    ordering = ("title",)
    list_filter = ("type",)
