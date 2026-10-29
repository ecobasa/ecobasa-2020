from django.utils.translation import gettext_lazy as _
from django import forms
from django.db.models import Q
from django.db.models.functions import Cast
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models import PointField
from django.contrib.gis.db.models.functions import Distance

import django_filters

from .models import Listing, ListingCategory, public_spot


# Plural labels here are deliberately distinct from Listing.TYPE_CHOICES (singular,
# used for a single listing's own badge/heading elsewhere) — these describe the
# filter's checkbox categories, e.g. "show me things in: Offers, Wishes, Skills".
_LISTING_TYPE_FILTER_CHOICES = [
    ("offer", _("Offers")),
    ("wish", _("Wishes")),
    ("skill", _("Skills")),
    ("need", _("Project needs")),
]

# What each type filter shows; several show what any of them shows
_TYPE_QUERIES = {
    "offer": Q(type=Listing.TYPE_OFFER),
    "wish": Q(type=Listing.TYPE_WISH),
    "skill": Q(kind__in=Listing.SKILL_KINDS),
    "need": Q(project__isnull=False, type=Listing.TYPE_WISH),
}


class ListingFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(label=_("Search"), method="do_search")
    type = django_filters.MultipleChoiceFilter(
        choices=_LISTING_TYPE_FILTER_CHOICES, widget=forms.CheckboxSelectMultiple, method="do_type",
    )
    kind = django_filters.MultipleChoiceFilter(
        label=_("Kind"), choices=Listing.KIND_CHOICES, widget=forms.CheckboxSelectMultiple
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
        fields = ["search", "type", "kind", "categories"]

    def do_type(self, queryset, name, value):
        query = Q()
        for key in value:
            query |= _TYPE_QUERIES[key]
        return queryset.filter(query) if value else queryset

    def do_search(self, queryset, name, value):
        from gift_economy.gifts.skills.models import skill_name_q
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(owner__name__icontains=value) |
            Q(community__name__icontains=value) |
            Q(project__title__icontains=value) |
            skill_name_q(value)
        )

    def do_location(self, queryset, name, value):
        try:
            lat, lon = map(float, value.split(","))
        except ValueError:
            return queryset
        loc = Point(lon, lat, srid=4326)
        # Where it is, a person's only by its cell: the distance tells nothing finer
        place = Cast(public_spot(), PointField(geography=True, srid=4326))
        return queryset.annotate(distance=Distance(place, loc)).order_by("distance")

    def do_location_name(self, queryset, name, value):
        return queryset  # NOOP
