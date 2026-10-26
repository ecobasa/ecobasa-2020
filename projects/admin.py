from django.contrib import admin

from .models import Need, Project


class NeedInline(admin.TabularInline):
    model = Need
    extra = 0
    fields = ("kind", "title", "skill", "quantity", "unit", "details", "category", "covered_at", "order")
    raw_id_fields = ("skill",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "community", "starts_on", "ends_on", "updated_at", "archived_at")
    list_filter = ("archived_at",)
    search_fields = ("title", "description", "community__name")
    raw_id_fields = ("community", "created_by")
    readonly_fields = ("created_at",)
    inlines = [NeedInline]
