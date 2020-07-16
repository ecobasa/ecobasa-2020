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

    class Meta:
        model = Ad
        fields = ["search", "type", "categories"]

    def do_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
