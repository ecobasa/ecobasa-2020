import io

import pytest
from django.core.management import call_command

from gift_economy.gifts.models import Listing
from gift_economy.gifts.things import WHITELISTED_KINDS, clear_cache, thing_named


@pytest.mark.django_db
def test_demo_data_names_things_as_the_form_would_and_spreads_them_over_the_map(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    clear_cache()
    call_command("seed_demo_data", stdout=io.StringIO())
    call_command("seed_demo_data", stdout=io.StringIO())  # safe to re-run
    things = Listing.objects.filter(kind__in=WHITELISTED_KINDS)
    # Tools, materials, vehicles, seeds and food only by a name from their vocabulary
    assert [(l.kind, l.title) for l in things if thing_named(l.title, l.kind) is None] == []
    assert all(l.thing_id for l in things)
    # Every kind of thing, in places of their own
    own_places = Listing.objects.filter(location__isnull=False, kind__in=Listing.THING_KINDS)
    assert set(own_places.values_list("kind", flat=True)) == set(Listing.THING_KINDS)
    assert own_places.values("location_name").distinct().count() >= 20
    window = Listing.objects.get(title="Wooden window")
    assert window.thing.slug == "wooden-window" and [c.slug for c in window.categories.all()] == ["building-renovation"]
    assert Listing.objects.get(title="Lamp").thing.kind == "material"
