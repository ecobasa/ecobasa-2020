import django_filters

from .models import Ad


class AdFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = Ad
        fields = ["title", "type"]
