"""The curated gift categories: areas of life in themes, loaded on every instance."""

import pytest

from ..management.commands.load_listing_categories import CATEGORIES
from ..models import ListingCategory


@pytest.mark.django_db
def test_the_migrations_load_the_themed_categories():
    assert list(ListingCategory.objects.values_list("slug", flat=True)) == [slug for _theme, slug, *_rest in CATEGORIES]
    # None of them says what the kind already says
    assert not ListingCategory.objects.filter(name__in=["Tools & Equipment", "Building Materials"]).exists()
