"""The curated gift categories: areas of life in themes, loaded on every instance."""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import translation

from users.models import User

from ..management.commands.load_listing_categories import CATEGORIES
from ..models import ListingCategory, themed_choices


@pytest.mark.django_db
def test_the_migrations_load_the_themed_categories():
    assert list(ListingCategory.objects.values_list("slug", flat=True)) == [slug for _theme, slug, *_rest in CATEGORIES]
    # None of them says what the kind already says
    assert not ListingCategory.objects.filter(name__in=["Tools & Equipment", "Building Materials"]).exists()
    garden = ListingCategory.objects.get(slug="garden-farm")
    with translation.override("de"):
        assert str(garden) == "Garten & Hof"
        assert themed_choices(ListingCategory.objects.all())[0] == ("Land & Ernährung", [
            (c.pk, str(c)) for c in ListingCategory.objects.filter(theme=ListingCategory.THEME_LAND)
        ])
    with translation.override("en"):
        assert str(garden) == "Garden & Farm"
        assert [theme for theme, _choices in themed_choices(ListingCategory.objects.all())] == [
            "Land & Food", "Building & Energy", "Home & Living", "On the Move", "Culture & Learning",
        ]


@pytest.mark.django_db
def test_the_form_collapses_the_categories_into_their_themes():
    user = User.objects.create_user(email="anna@example.com", password="x", name="Anna")
    client = Client()
    client.force_login(user)
    page = client.get(reverse("gifts:create"), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    # The themes first, each opening into its categories
    assert page.index("Land &amp; Food") < page.index("Building &amp; Energy") < page.index('data-theme="land"')
    assert page.index('data-theme="land"') < page.index("Seeds &amp; Plants") < page.index('data-theme="building"')
    assert "fa-seedling" in page
