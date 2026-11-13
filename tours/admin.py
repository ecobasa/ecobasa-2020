from django.contrib import admin

from .models import Stop, Tour, Vehicle


class StopInline(admin.TabularInline):
    model = Stop
    extra = 0
    fields = ("order", "event", "community", "name", "country", "arrive_on", "leave_on", "leave_at", "flexible")
    raw_id_fields = ("event", "community")


class VehicleInline(admin.TabularInline):
    model = Vehicle
    extra = 0
    fields = ("label", "image", "drivers", "seats", "sleeps", "note", "needs_driver", "from_stop", "to_stop")
    raw_id_fields = ("drivers", "from_stop", "to_stop")


@admin.register(Tour)
class TourAdmin(admin.ModelAdmin):
    list_display = ("title", "organiser", "starts_on", "ends_on", "open_to_join", "listed", "published_at", "archived_at")
    list_filter = ("travel_mode", "open_to_join", "listed", "archived_at")
    search_fields = ("title", "description", "organiser__name", "organiser__email")
    raw_id_fields = ("organiser",)
    filter_horizontal = ("learn_skills",)
    readonly_fields = ("slug", "created_at", "route", "distance_km", "starts_on", "ends_on")
    inlines = [StopInline, VehicleInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.rebuild_route()
