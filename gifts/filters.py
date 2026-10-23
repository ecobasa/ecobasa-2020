from django.utils.translation import gettext_lazy as _
from django import forms
from django.db.models import Q
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

import django_filters

from .models import Listing, ListingCategory


# Plural labels here are deliberately distinct from Listing.TYPE_CHOICES (singular,
# used for a single listing's own badge/heading elsewhere) — these describe the
# filter's checkbox categories, e.g. "show me things in: Offers, Wishes, Skills".
_LISTING_TYPE_FILTER_CHOICES = [
    ("offer", _("Offers")),
    ("wish", _("Wishes")),
    ("skill", _("Skills")),
]


class ListingFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(label=_("Search"), method="do_search")
    type = django_filters.MultipleChoiceFilter(
        choices=_LISTING_TYPE_FILTER_CHOICES, widget=forms.CheckboxSelectMultiple
    )
    categories = django_filters.ModelMultipleChoiceFilter(
        queryset=ListingCategory.objects.all(), widget=forms.CheckboxSelectMultiple
    )
    location = django_filters.CharFilter(label=_("Location"), method="do_location")
    location_name = django_filters.CharFilter(
        label=_("Location"), method="do_location_name"
    )

    class Meta:
        model = Listing
        fields = ["search", "type", "categories"]

    def do_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(owner__name__icontains=value)
        )

    def do_location(self, queryset, name, value):
        try:
            lat, lon = map(float, value.split(","))
        except ValueError:
            return queryset
        loc = Point(lon, lat, srid=4326)
        return queryset.annotate(distance=Distance("location", loc)).order_by("distance")

    def do_location_name(self, queryset, name, value):
        return queryset  # NOOP
