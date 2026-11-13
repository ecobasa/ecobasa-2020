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
    # Cocoa from the cacao farm sails to Portugal, where Ana agreed to receive it
    from tours.models import Delivery
    delivery = Delivery.objects.get(tour__title="Across the Atlantic by sail")
    assert (delivery.offer.title, delivery.wish.owner.email, delivery.status) == ("Cocoa beans", "ana@ecobasa.demo", Delivery.STATUS_AGREED)
    # The boat it looked for is lent by Nils, who doesn't sail along
    need = Listing.objects.get(tour=delivery.tour, title="Sailing boat")
    assert need.status == Listing.STATUS_PROMISED and need.promised_by()[0].email == "nils@ecobasa.demo"
    assert not delivery.tour.travellers.filter(user__email="nils@ecobasa.demo").exists()
    # Every tour with a route has something to take along
    from tours.deliveries import delivery_suggestions
    from tours.models import Tour
    for tour in Tour.objects.all():
        if tour.stops.count() > 1:
            assert delivery_suggestions(tour), tour.title
    # More success stories than the homepage shows at once, all of them positive and shared
    from gift_economy.references.models import Reference
    featured = Reference.objects.filter(featured_at__isnull=False)
    assert featured.count() == 4
    assert all(r.share_publicly and r.impression == Reference.IMPRESSION_POSITIVE for r in featured)
