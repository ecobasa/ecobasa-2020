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
    # A tour that is over: cocoa from the cacao farm sailed to Portugal and was handed to Ana
    from tours.models import Delivery
    delivery = Delivery.objects.get(tour__title="Across the Atlantic by sail")
    atlantic = delivery.tour
    assert atlantic.is_over and atlantic.organiser.email == "jules@ecobasa.demo"
    assert (delivery.offer.title, delivery.wish.owner.email, delivery.status) == ("Cocoa beans", "ana@ecobasa.demo", Delivery.STATUS_HANDED_OVER)
    # The boat it looked for is Nils's, who sailed the first leg: the tour's vehicle
    need = Listing.objects.get(tour=atlantic, title="Sailing boat")
    assert need.promised_by()[0].email == "nils@ecobasa.demo"
    assert [(v.label, v.listing.owner.email) for v in atlantic.vehicles.all()] == [("Albatroz", "nils@ecobasa.demo")]
    # What they wrote afterwards is told at the stops where it happened
    from django.contrib.auth.models import AnonymousUser
    from tours.timeline import timeline_by_stop
    stops = atlantic.ordered_stops()
    told = [{e["reference"].author.email for e in entries if e["kind"] == "reference"} for entries in timeline_by_stop(atlantic, stops, AnonymousUser())]
    assert told[4] == {"valeria@ecobasa.demo", "jules@ecobasa.demo", "diego@ecobasa.demo", "sam@ecobasa.demo"}
    assert told[6] == {"jules@ecobasa.demo", "nils@ecobasa.demo"} and "ana@ecobasa.demo" in told[7]
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
    # Gift-circles: last week's Giftsheet closed into a wish, a ladder to lend and their matches
    from events.models import Event
    from gift_economy.gift_circles.models import Entry
    last = Event.objects.get(title="Gift-circle by the river")
    assert last.giftsheet.is_closed and last.next_ones.get().max_people == 12
    sofa = Entry.objects.get(event=last, text__startswith="Help carrying a sofa")
    assert sofa.match.from_user.email == "sam@ecobasa.demo" and sofa.listing.covered_at is not None
    ladder = Entry.objects.get(event=last, text="A long ladder")
    assert ladder.listing.lend and ladder.match.from_user.email == "bjorn@ecobasa.demo"
    assert Entry.objects.get(event=last, text__startswith="A bike trailer").listing is None  # Sam said no
    assert Event.objects.get(title__startswith="Gift-circle online").timezone == "Europe/Paris"
