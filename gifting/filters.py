from django.utils.translation import gettext_lazy as _
from django import forms
from django.db.models import Q

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

    class Meta:
        model = Ad
        fields = ["search", "type", "categories"]

    def do_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )

    def filter_by_me(self, queryset, name, value):
        if value and self.request and self.request.user.is_authenticated:
            return queryset.filter(owner=self.request.user)
        return queryset

