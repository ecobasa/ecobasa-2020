from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from communities.models import Community
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match
from gift_economy.references.models import ReferenceRequest, match_reference_subject, reference_choices
from gift_economy.references.reference_requests import send_reference_requests
from users.models import User

from .. import deliveries
from ..models import Delivery, Traveller
from .test_joining import person  # noqa: F401
from .test_tours import farm, login, organiser, other, project, published, village  # noqa: F401

pytestmark = pytest.mark.django_db

# Invented places: Leipzig between the farm near Potsdam and the village near Dresden,
# someone living halfway between the farm and Leipzig, right by the route, and Munich,
# far from it
LEIPZIG = Point(12.37, 51.34, srid=4326)
BY_THE_ROUTE = Point(12.72, 51.87, srid=4326)
MUNICH = Point(11.58, 48.14, srid=4326)


@pytest.fixture
def east(organiser, farm, village, project):
    """Lindenhof (1), Leipzig (2), the rocket stove at Elbtal (3), with days."""
    village.owner = User.objects.create_user(email="elke@example.com", password="secret", name="Elke")
    village.save()
    today = timezone.localdate()
    return published(
        organiser, "Clay and seeds",
        {"community": farm, "arrive_on": today + timedelta(days=10), "leave_on": today + timedelta(days=14)},
        {"name": "Leipzig", "location": LEIPZIG, "country": "DE"},
        {"event": project, "arrive_on": today + timedelta(days=20), "leave_on": today + timedelta(days=30)},
    )


def thing(type, title, kind=Listing.KIND_MATERIAL, **fields):
    return Listing.objects.create(type=type, kind=kind, title=title, **fields)


def suggested(tour):
    return {(pair.offer.title, pair.wish.title) for pair in deliveries.delivery_suggestions(tour)}


def take(tour, user, pair, **data):
    return login(user).post(reverse("tours:delivery_take", args=[tour.slug]), {
        "pair": pair.key, "to_giver": "Could I take it along?", "to_receiver": "Shall I bring it?", **data,
    })


def accept(match):
    return login(match.recipient).post(match.get_absolute_url(), {"action": "accept"})


# ── What could travel ──────────────────────────────────────────────

def test_a_fitting_pair_is_suggested_only_in_route_order(east, farm, village, project):
    thing("offer", "Clay", community=farm, quantity=40, unit="kg")
    thing("wish", "Clay", event=project, quantity=20, unit="kg")
    # The other way round: offered further on, wished for before
    thing("offer", "Straw bales", community=village)
    thing("wish", "Straw", community=farm)
    pairs = deliveries.delivery_suggestions(east)
    assert [(p.offer.title, p.wish.title, p.pickup.label, p.dropoff.label, p.amount) for p in pairs] == [
        ("Clay", "Clay", "Lindenhof", "Rocket stove", "20 kg"),
    ]


def test_skills_and_things_to_lend_dont_travel(east, farm, project):
    thing("offer", "Ladder", kind=Listing.KIND_TOOL, community=farm, lend=True)
    thing("wish", "Ladder", kind=Listing.KIND_TOOL, event=project, lend=True)
    thing("offer", "Clay plastering", kind=Listing.KIND_KNOWLEDGE, community=farm)
    thing("wish", "Clay plastering", kind=Listing.KIND_KNOWLEDGE, event=project)
    assert suggested(east) == set()


def test_seeds_respect_the_climate_rule(organiser):
    """Seeds from the tropics don't grow in Brandenburg; cocoa beans to eat travel anyway."""
    cacao = Community.objects.create(
        name="Selva Viva", location=Point(-60.02, -3.12, srid=4326), country="BR", location_public=True,
        owner=User.objects.create_user(email="rio@example.com", password="secret", name="Rio"),
    )
    garden = Community.objects.create(
        name="Gartenhof", location=Point(13.06, 52.40, srid=4326), country="DE", location_public=True,
        owner=User.objects.create_user(email="gerd@example.com", password="secret", name="Gerd"),
    )
    tour = published(organiser, "Across", {"community": cacao}, {"community": garden})
    thing("offer", "Cacao", kind=Listing.KIND_SEEDS_PLANTS, community=cacao)
    thing("wish", "Cacao", kind=Listing.KIND_SEEDS_PLANTS, community=garden)
    thing("offer", "Cocoa beans", kind=Listing.KIND_FOOD, community=cacao)
    thing("wish", "Cocoa beans", kind=Listing.KIND_FOOD, community=garden)
    assert suggested(tour) == {("Cocoa beans", "Cocoa beans")}


def test_only_travellers_on_the_stretch_can_take_it(east, farm, project, organiser, other):
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    stops = east.ordered_stops()
    # Gets on in Leipzig: after the clay was picked up
    Traveller.objects.create(tour=east, user=other, from_stop=stops[1], to_stop=stops[2])
    pair = deliveries.delivery_suggestions(east)[0]
    assert pair.bringers == [organiser.pk]
    # The one who gets on later sees who could take it instead
    page = login(other).get(reverse("tours:deliveries", args=[east.slug])).content.decode()
    assert "could take it" in page and organiser.get_absolute_url() in page
    assert take(east, other, pair).status_code == 302
    assert not Delivery.objects.exists()


def test_a_travellers_own_gift_goes_to_a_host_and_to_someone_by_the_route(east, project, other):
    """A cargo bike a traveller gives away is a gift like any other: it travels only
    where someone wishes for one."""
    stops = east.ordered_stops()
    Traveller.objects.create(tour=east, user=other, from_stop=stops[0], to_stop=stops[2])
    thing("offer", "Cargo bike", kind=Listing.KIND_VEHICLE, owner=other)
    assert suggested(east) == set()
    thing("wish", "Cargo bike", kind=Listing.KIND_VEHICLE, event=project)
    neighbour = User.objects.create_user(email="nele@example.com", password="secret", name="Nele", location=BY_THE_ROUTE)
    far = User.objects.create_user(email="fritz@example.com", password="secret", name="Fritz", location=MUNICH)
    thing("wish", "Cargo bike", kind=Listing.KIND_VEHICLE, owner=neighbour)
    thing("wish", "Cargo bike", kind=Listing.KIND_VEHICLE, owner=far)
    pairs = deliveries.delivery_suggestions(east)
    assert [(p.wish.holder_name, p.own, p.bringers, p.dropoff.stop) for p in pairs] == [
        ("Nele", True, [other.pk], None), ("Elbtal", True, [other.pk], stops[2]),
    ]
    # Only asked of the receiver: it is theirs to give
    response = take(east, other, pairs[1])
    delivery = Delivery.objects.get()
    assert response.status_code == 302 and delivery.pickup_match is None and not delivery.needs_pickup
    assert delivery.handover_match.recipient == project.community.owner
    assert {c.listing.title for c in delivery.handover_match.contributions.all()} == {"Cargo bike"}


def test_picked_up_on_the_way(east, project):
    """An offer of someone living by the route, picked up between two stops."""
    neighbour = User.objects.create_user(email="nele@example.com", password="secret", name="Nele",
                                         location=BY_THE_ROUTE, location_name="Wittenberg")
    thing("offer", "Clay", owner=neighbour)
    thing("wish", "Clay", event=project)
    pair = deliveries.delivery_suggestions(east)[0]
    assert pair.pickup.stop is None and 0 < pair.pickup.position < 1 and pair.needs_pickup
    assert pair.pickup.label == "Wittenberg"


def test_not_this_hides_the_pair(east, farm, project, organiser):
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    pair = deliveries.delivery_suggestions(east)[0]
    login(organiser).post(reverse("tours:delivery_dismiss", args=[east.slug]), {"pair": pair.key})
    assert suggested(east) == set()
    assert Delivery.objects.get().status == Delivery.STATUS_DISMISSED


def test_the_page_is_for_who_travels(east, other, organiser):
    url = reverse("tours:deliveries", args=[east.slug])
    assert login(other).get(url).status_code == 403
    assert login(organiser).get(url).status_code == 200


# ── Taken along ────────────────────────────────────────────────────

def test_clay_from_the_first_stop_to_the_project_at_the_third(east, farm, village, project, organiser):
    clay = thing("offer", "Clay", community=farm, quantity=40, unit="kg")
    need = thing("wish", "Clay", event=project, quantity=20, unit="kg")
    pair = deliveries.delivery_suggestions(east)[0]
    # Organisers find it in the planner, under what is recommended on the way
    page = login(organiser).get(reverse("tours:plan", args=[east.slug])).content.decode()
    assert "Could travel with you" in page and "ll take it" in page

    mail.outbox.clear()
    take(east, organiser, pair, quantity=15)
    delivery = Delivery.objects.get()
    giver, receiver = delivery.pickup_match, delivery.handover_match
    assert (giver.target, giver.recipient, receiver.target, receiver.recipient) == (clay, farm.owner, need, village.owner)
    assert [c.quantity for c in giver.contributions.all()] == [15]
    assert [c.quantity for c in receiver.contributions.all()] == [15]
    # With the stops' days
    assert timezone.localdate(giver.proposed_date) == east.ordered_stops()[0].arrive_on
    assert sorted(m.to[0] for m in mail.outbox) == sorted([farm.owner.email, village.owner.email])
    assert "would take your offer along on their tour" in mail.outbox[0].subject + mail.outbox[0].body + mail.outbox[1].body
    assert delivery.status == Delivery.STATUS_ASKED
    # The match page says what it is
    assert "Clay and seeds" in login(farm.owner).get(giver.get_absolute_url()).content.decode()
    assert giver.kind[0] == "Delivery"

    accept(giver)
    accept(receiver)
    delivery.refresh_from_db()
    assert delivery.status == Delivery.STATUS_AGREED
    packing = deliveries.packing_list(east, [delivery])
    assert [(spot.label, [what for what, _d in items]) for spot, _n, items in packing] == [
        ("Lindenhof", ["pick"]), ("Rocket stove", ["hand"]),
    ]
    # Not asked for references yet: it hasn't happened
    later = timezone.now() + timedelta(days=60)
    assert send_reference_requests(now=later) == 0

    client = login(organiser)
    client.post(reverse("tours:delivery_picked_up", args=[east.slug, delivery.pk]))
    delivery.refresh_from_db()
    assert delivery.status == Delivery.STATUS_ON_BOARD
    client.post(reverse("tours:delivery_handed_over", args=[east.slug, delivery.pk]))
    delivery.refresh_from_db()
    need.refresh_from_db()
    assert delivery.status == Delivery.STATUS_HANDED_OVER
    # 15 of 20 kg: still open for the rest
    assert need.status == Listing.STATUS_OFFERED and need.covered_at is None and need.remaining == 5

    # Everyone involved is asked once it was handed over
    due = timezone.now() + timedelta(days=settings.REFERENCE_REQUEST_DELAY_DAYS, hours=1)
    assert send_reference_requests(now=due) == 4
    asked = {(r.match_id, r.user_id) for r in ReferenceRequest.objects.all()}
    assert asked == {(giver.pk, organiser.pk), (giver.pk, farm.owner.pk), (receiver.pk, organiser.pk), (receiver.pk, village.owner.pk)}
    # The bringer writes about the communities, with the gift's name; the giver and the
    # receiver about the tour or the one who brought it
    assert match_reference_subject(giver, organiser) == (farm, "Clay", "")
    assert match_reference_subject(receiver, organiser) == (village, "Clay", "")
    assert [subject for _key, subject in reference_choices(receiver, village.owner)] == [east, organiser]
    assert match_reference_subject(receiver, village.owner) == (east, "Clay", "")

    # Shown where it matters
    assert "Rocket stove" in login(organiser).get(east.get_absolute_url()).content.decode()
    assert "Clay and seeds" in login(farm.owner).get(clay.get_absolute_url()).content.decode()
    assert "Clay and seeds" in login(farm.owner).get(village.get_absolute_url()).content.decode()


def test_a_wish_handed_over_in_full_counts_as_covered(east, farm, project, organiser):
    thing("offer", "Clay", community=farm, quantity=40, unit="kg")
    need = thing("wish", "Clay", event=project, quantity=20, unit="kg")
    take(east, organiser, deliveries.delivery_suggestions(east)[0])
    delivery = Delivery.objects.get()
    accept(delivery.pickup_match)
    accept(delivery.handover_match)
    deliveries.picked_up(delivery)
    deliveries.handed_over(delivery)
    need.refresh_from_db()
    assert need.status == Listing.STATUS_COVERED


def test_a_declined_side_marks_the_delivery_as_fallen_through(east, farm, project, organiser):
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    take(east, organiser, deliveries.delivery_suggestions(east)[0])
    delivery = Delivery.objects.get()
    login(delivery.handover_match.recipient).post(delivery.handover_match.get_absolute_url(), {"action": "decline"})
    delivery.refresh_from_db()
    assert delivery.status == Delivery.STATUS_FELL_THROUGH
    assert delivery.open_match_left() == delivery.pickup_match
    page = login(organiser).get(reverse("tours:deliveries", args=[east.slug])).content.decode()
    assert "Take your request to Ana back too?" in page

    login(organiser).post(reverse("tours:delivery_withdraw", args=[east.slug, delivery.pk]))
    delivery.pickup_match.refresh_from_db()
    assert delivery.pickup_match.status == Match.STATUS_WITHDRAWN
    # Not on the tour page for others any more, nor suggested again
    assert 'id="deliveries"' not in login(farm.owner).get(east.get_absolute_url()).content.decode()
    assert suggested(east) == set()


def test_a_personal_tour_is_seen_by_the_givers_and_receivers_of_its_deliveries(organiser, farm, village, project):
    village.owner = User.objects.create_user(email="elke@example.com", password="secret", name="Elke")
    village.save()
    tour = published(organiser, "Just me", {"community": farm}, {"event": project}, open_to_join=False, listed=False)
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    stranger = person("Sven")
    assert not tour.can_view(farm.owner) and not tour.can_view(stranger)
    take(tour, organiser, deliveries.delivery_suggestions(tour)[0])
    assert tour.can_view(farm.owner) and tour.can_view(village.owner)
    assert not tour.can_view(stranger)


def test_arcs_on_the_tour_map(east, farm, project, organiser):
    from ..geo import delivery_features

    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    take(east, organiser, deliveries.delivery_suggestions(east)[0])
    (feature,) = delivery_features(east, list(east.deliveries.all()))
    coords = feature["geometry"]["coordinates"]
    stops = east.ordered_stops()
    assert coords[0] == list(stops[0].public_place()[1].coords) and coords[-1] == list(stops[2].public_place()[1].coords)
    # A curve, not the straight line
    middle = coords[len(coords) // 2]
    assert middle != [(coords[0][0] + coords[-1][0]) / 2, (coords[0][1] + coords[-1][1]) / 2]


def test_an_ambassador_takes_their_communitys_gift_without_asking_themself(east, farm, project):
    stops = east.ordered_stops()
    Traveller.objects.create(tour=east, user=farm.owner, from_stop=stops[0], to_stop=stops[2])
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    pair = deliveries.delivery_suggestions(east)[0]
    assert farm.owner.pk in pair.bringers
    take(east, farm.owner, pair, to_giver="")
    delivery = Delivery.objects.get()
    assert delivery.pickup_match is None and not delivery.needs_pickup
    accept(delivery.handover_match)
    delivery.refresh_from_db()
    assert delivery.status == Delivery.STATUS_AGREED and delivery.can_hand_over


def test_the_list_map_has_the_arcs_of_each_tour(east, farm, project, organiser):
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    take(east, organiser, deliveries.delivery_suggestions(east)[0])
    features = login(organiser).get(reverse("tours:api-routes"), {"bbox": "12,50,15,53"}).json()["features"]
    arcs = [f for f in features if f["properties"]["kind"] == "delivery"]
    assert [(f["properties"]["slug"], f["properties"]["name"]) for f in arcs] == [(east.slug, "Clay")]


def test_cocoa_beans_are_food_and_seeds():
    from gift_economy.gifts.things import clear_cache, recognize

    clear_cache()
    food = recognize("Cocoa beans", Listing.KIND_FOOD)
    seeds = recognize("Kakaobohnen", Listing.KIND_SEEDS_PLANTS)
    from gift_economy.gifts.models import Thing

    assert Thing.objects.get(pk=food).slug == "food-cocoa-beans"
    assert Thing.objects.get(pk=seeds).slug == "cacao"


def test_the_planner_comes_back_to_itself_and_others_who_travel_see_it_on_the_deliveries_page(east, farm, project, organiser, other):
    thing("offer", "Clay", community=farm)
    thing("wish", "Clay", event=project)
    pair = deliveries.delivery_suggestions(east)[0]
    response = take(east, organiser, pair, next=reverse("tours:plan", args=[east.slug]))
    assert response.url == reverse("tours:plan", args=[east.slug]) + "#could-travel"

    thing("offer", "Straw", community=farm)
    thing("wish", "Straw", event=project)
    Traveller.objects.create(tour=east, user=other)
    page = login(other).get(reverse("tours:deliveries", args=[east.slug])).content.decode()
    assert "Straw" in page and "ll take it" in page
