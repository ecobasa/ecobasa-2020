from django.utils.translation import gettext_lazy as _
from django import forms
from django.db.models import Q
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

import django_filters

from .models import Ad, AdCategory


_AD_TYPE_CHOICES = list(Ad.TYPE_CHOICES) + [("skill", _("Skills"))]


class AdFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(label=_("Search"), method="do_search")
    type = django_filters.MultipleChoiceFilter(
        choices=_AD_TYPE_CHOICES, widget=forms.CheckboxSelectMultiple
    )
    categories = django_filters.ModelMultipleChoiceFilter(
        queryset=AdCategory.objects.all(), widget=forms.CheckboxSelectMultiple
    )
    location = django_filters.CharFilter(label=_("Location"), method="do_location")
    location_name = django_filters.CharFilter(
        label=_("Location"), method="do_location_name"
    )

    class Meta:
        model = Ad
        fields = ["search", "type", "categories"]

    def do_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) |
            Q(description__icontains=value) |
            Q(owner__name__icontains=value)
        )

    def do_location(self, queryset, name, value):
        lat, lon = value.split(",")
        loc = Point(float(lon), float(lat), srid=4326)
        return queryset.annotate(distance=Distance("location", loc)).order_by("distance")

    def do_location_name(self, queryset, name, value):
        return queryset  # NOOP
