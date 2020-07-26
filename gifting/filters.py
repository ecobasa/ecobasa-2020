from django.utils.translation import gettext_lazy as _
from django import forms
from django.db.models import Q
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

import django_filters

from .models import Ad, AdCategory


class AdFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(label=_("Search"), method="do_search")
    type = django_filters.MultipleChoiceFilter(
        choices=Ad.TYPE_CHOICES, widget=forms.CheckboxSelectMultiple
    )
    categories = django_filters.ModelMultipleChoiceFilter(
        queryset=AdCategory.objects.all(), widget=forms.CheckboxSelectMultiple
    )
    from_me = django_filters.BooleanFilter(
        label=_("From Me"), method="filter_by_me", widget=forms.CheckboxInput
    )
    location = django_filters.CharFilter(label=_("Location"), method="do_location")
    location_name = django_filters.CharFilter(
        label=_("Location"), method="do_location_name"
    )

    class Meta:
        model = Ad
        fields = ["search", "type", "categories"]

    def do_search(self, queryset, name, value):
        """Search for value in title and description"""
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )

    def filter_by_me(self, queryset, name, value):
        """Only show ads by current user (if authenticated)"""
        if value and self.request and self.request.user.is_authenticated:
            return queryset.filter(owner=self.request.user)
        return queryset

    def do_location(self, queryset, name, value):
        """Order by distance to given location"""
        x, y = value.split(",")
        x = float(x)
        y = float(y)
        loc = Point(x, y, srid=4326)
        return queryset.annotate(distance=Distance("location", loc)).order_by(
            "distance"
        )

    def do_location_name(self, queryset, name, value):
        return queryset  # NOOP
