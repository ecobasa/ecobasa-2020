from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.utils import timezone

from communities.models import Community
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import get_or_create_skill
from gift_economy.gifts.testing import skill_offer, skill_wish
from gift_economy.references.models import Reference
from users.models import User

from .. import recommend
from ..models import Stop
from ..recommend import best_position, hints, recommend_stops, suggest_order
from .test_joining import person
from .test_tours import FARM_POINT, VILLAGE_POINT, add, exact, farm, login, organiser, other, published, village  # noqa: F401

pytestmark = pytest.mark.django_db

# Invented places: halfway between the farm near Potsdam and the village near Dresden,
# right on the line between them; and a spot about 70 km west of it
ON_THE_WAY = Point(13.40, 51.75, srid=4326)
OFF_THE_WAY = Point(12.40, 51.75, srid=4326)


def host(name, point=ON_THE_WAY, public=True, **fields):
    ambassador = User.objects.create_user(email=f"{name.lower()}@example.org", password="secret", name=f"Ambassador {name}")
    return Community.objects.create(
        name=name, ambassador=ambassador, location=point, country="DE", location_name=f"{name}, Deutschland",
        location_public=public, **fields,
    )


def names(tour, **kwargs):
    return [rec.name for rec in recommend_stops(tour, **kwargs)]


@pytest.fixture
def east(organiser, farm, village):
    """Farm to village, with days, so there is a window to fit an event and a stay in."""
    today = timezone.localdate()
    return published(
        organiser, "Clay and seeds",
        {"community": farm, "arrive_on": today + timedelta(days=10), "leave_on": today + timedelta(days=17)},
        {"community": village, "arrive_on": today + timedelta(days=30), "leave_on": today + timedelta(days=37)},
        max_people=4,
    )


@pytest.fixture
def twins():
    """Two communities at the same place: alike, Aaa comes first by name."""
    return host("Aaa"), host("Zzz")


@pytest.fixture
def twin_events():
    """Two ongoing events at one community: alike, Aaa comes first by title."""
    community = host("Mitte")
    return (Event.objects.create(community=community, title="Aaa gathering"),
            Event.objects.create(community=community, title="Zzz gathering"))


def reason_keys(tour, name, **kwargs):
    rec = next(rec for rec in recommend_stops(tour, **kwargs) if rec.name == name)
    return {reason.key for reason in rec.reasons}


# ── Each reason alone moves a candidate up ─────────────────────────

def test_alike_candidates_are_in_name_order(east, twins):
    assert names(east) == ["Aaa", "Zzz"]
    assert reason_keys(east, "Aaa") == {"way"}


def test_what_the_tour_wants_to_learn_moves_one_up(east, twins):
    permaculture = get_or_create_skill("Permaculture")[0]
    east.learn_skills.add(permaculture)
    skill_offer(twins[1], permaculture)
    assert names(east)[0] == "Zzz"
    assert "learn" in reason_keys(east, "Zzz")


def test_a_need_the_travellers_can_cover_moves_one_up(east, twins, organiser):
    carpentry = get_or_create_skill("Carpentry")[0]
    skill_offer(organiser, carpentry)
    skill_wish(twins[1], carpentry)
    assert names(east)[0] == "Zzz"
    assert "needs" in reason_keys(east, "Zzz")


def test_room_for_the_group_moves_one_up_and_no_room_down(east, twins):
    zzz = twins[1]
    zzz.max_guests = 6
    zzz.save()
    assert names(east)[0] == "Zzz"
    assert "room" in reason_keys(east, "Zzz")
    zzz.max_guests = 0
    zzz.save()
    assert names(east) == ["Aaa", "Zzz"]
    assert "little_room" in reason_keys(east, "Zzz")


def test_gifts_that_could_travel_move_one_up(east, twins, farm):
    Listing.objects.create(type=Listing.TYPE_WISH, kind=Listing.KIND_MATERIAL, title="Clay", community=farm)
    Listing.objects.create(type=Listing.TYPE_OFFER, kind=Listing.KIND_MATERIAL, title="Clay from our pond", community=twins[1])
    assert names(east)[0] == "Zzz"
    assert "gifts" in reason_keys(east, "Zzz")


def test_an_active_ambassador_moves_one_up(east, twins):
    ambassador = twins[1].ambassador
    ambassador.last_seen = timezone.now()
    ambassador.save()
    assert names(east)[0] == "Zzz"


def test_references_move_one_up(east, twins, other):
    Reference.objects.create(author=other, recipient=twins[1].ambassador, subject=twins[1], text="Warm welcome.")
    assert names(east)[0] == "Zzz"
    assert "references" in reason_keys(east, "Zzz")


def test_an_event_in_the_tours_days_moves_it_up(east, twin_events):
    zzz = twin_events[1]
    zzz.starts_on, zzz.ends_on = east.starts_on + timedelta(days=12), east.starts_on + timedelta(days=14)
    zzz.save()
    order = [name for name in names(east) if name.endswith("gathering")]
    assert order == ["Zzz gathering", "Aaa gathering"]
    assert "days" in reason_keys(east, "Zzz gathering")


@pytest.mark.parametrize("provided", ["food_provided", "bed_provided"])
def test_food_or_a_bed_moves_an_event_up(east, twin_events, provided):
    zzz = twin_events[1]
    setattr(zzz, provided, True)
    zzz.save()
    order = [name for name in names(east) if name.endswith("gathering")]
    assert order == ["Zzz gathering", "Aaa gathering"]


def test_being_on_the_way_moves_one_up(east):
    permaculture = get_or_create_skill("Permaculture")[0]
    east.learn_skills.add(permaculture)
    for community in (host("Aaa", OFF_THE_WAY), host("Zzz", ON_THE_WAY)):
        skill_offer(community, permaculture)
    assert names(east, area_km=100) == ["Zzz", "Aaa"]
    assert reason_keys(east, "Aaa", area_km=100) == {"learn"}


def test_nothing_without_a_reason(east):
    host("Aaa", OFF_THE_WAY)
    assert names(east, area_km=100) == []


# ── Which candidates, and where ────────────────────────────────────

def test_the_cap_on_candidates_holds(east, monkeypatch):
    for i in range(5):
        host(f"Place {i}", Point(13.40 + i * 0.05, 51.75, srid=4326))
    monkeypatch.setattr(recommend, "MAX_CANDIDATES", 3)
    found = names(east, area_km=100)
    # The three nearest the route
    assert sorted(found) == ["Place 0", "Place 1", "Place 2"]


def test_no_community_without_an_ambassador_nor_the_stops_already_there(east, farm, village):
    Community.objects.create(name="Nobody's", location=ON_THE_WAY, country="DE", location_public=True)
    assert names(east) == []


def test_a_community_with_an_event_on_the_route_only_with_its_other_events(organiser, village):
    mitte = host("Mitte")
    fest = Event.objects.create(community=mitte, title="Harvest")
    Event.objects.create(community=mitte, title="Open day")
    tour = published(organiser, "Fest", {"event": fest}, {"community": village})
    assert names(tour) == ["Open day"]


def test_best_position_between_two_stops(east):
    points = [stop.public_place()[1] for stop in east.ordered_stops()]
    position, km = best_position(points, ON_THE_WAY)
    assert position == 1 and km < 10
    position, _km = best_position(points, Point(14.5, 50.0, srid=4326))
    assert position == 2


def test_learning_tour_with_one_stop(organiser, village):
    """Wanting to learn permaculture and yoga with one stop: communities and events on
    the way that teach either, each with its reasons; adding one updates route and list."""
    tour = published(organiser, "Learning", {"community": village})
    permaculture, yoga = get_or_create_skill("Permaculture")[0], get_or_create_skill("Yoga")[0]
    tour.learn_skills.add(permaculture, yoga)
    garden = host("Garden", Point(13.9, 51.1, srid=4326))
    skill_offer(garden, permaculture)
    retreat = host("Retreat", Point(13.6, 51.0, srid=4326))
    week = Event.objects.create(community=retreat, title="Yoga week")
    skill_offer(retreat, yoga, event=week)
    host("Quiet", Point(13.7, 51.2, srid=4326))

    recs = recommend_stops(tour)
    learning = {rec.name for rec in recs if any(r.key == "learn" for r in rec.reasons)}
    assert learning == {"Garden", "Yoga week"}
    assert [rec.name for rec in recs][:2] in (["Garden", "Yoga week"], ["Yoga week", "Garden"])

    client = login(organiser)
    response = client.post(reverse("tours:plan_add", args=[tour.slug]), {
        "community": garden.pk, "position": 1, "km": 50,
    }, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    tour.refresh_from_db()
    assert [stop.label for stop in tour.ordered_stops()] == ["Elbtal", "Garden"]
    assert tour.route is not None
    html = response.content.decode()
    assert 'id="planner"' in html and "Yoga week" in html
    # Garden is a stop now, no longer recommended
    assert 'name="community" value="%s"' % garden.pk not in html


def test_adding_an_event_inserts_it_with_its_days(east, organiser):
    community = host("Mitte")
    today = timezone.localdate()
    fest = Event.objects.create(community=community, title="Harvest", starts_on=today + timedelta(days=20),
                                ends_on=today + timedelta(days=22))
    login(organiser).post(reverse("tours:plan_add", args=[east.slug]), {"event": fest.pk, "position": 1})
    stops = east.ordered_stops()
    assert [stop.label for stop in stops] == ["Lindenhof", "Harvest", "Elbtal"]
    assert (stops[1].arrive_on, stops[1].leave_on) == (fest.starts_on, fest.ends_on)


def test_only_organisers_add(east, other):
    response = login(other).post(reverse("tours:plan_add", args=[east.slug]), {"community": host("Aaa").pk, "position": 0})
    assert response.status_code == 403
    assert east.stops.count() == 2


def test_the_planner_gives_no_private_door_away(east, organiser):
    door = Point(13.4123, 51.7456, srid=4326)
    hidden = host("Hidden", door, public=False)
    html = login(organiser).get(reverse("tours:plan", args=[east.slug])).content.decode()
    assert "Hidden" in html
    assert not exact(door, html)
    assert not exact(FARM_POINT, html)
    assert hidden.rough_place()[1] is not None


# ── An order with fewer km ──────────────────────────────────────────

def line_tour(organiser, *stops):
    return published(organiser, "Line", *[
        {"name": name, "location": Point(lon, 50.0, srid=4326), **days} for name, lon, days in stops
    ])


def test_suggest_an_order_with_fewer_km(organiser):
    tour = line_tour(organiser, ("A", 10.0, {}), ("C", 12.0, {}), ("B", 11.0, {}), ("D", 13.0, {}))
    order = suggest_order(tour.ordered_stops())
    labels = [stop.label for stop in order]
    assert labels in (["A", "B", "C", "D"], ["D", "C", "B", "A"])


def test_stops_with_days_keep_their_order(organiser):
    today = timezone.localdate()
    tour = line_tour(
        organiser, ("A", 10.0, {}), ("C", 12.0, {"arrive_on": today}), ("B", 11.0, {"arrive_on": today + timedelta(days=5)}),
        ("D", 13.0, {}),
    )
    order = [stop.label for stop in suggest_order(tour.ordered_stops())]
    assert order.index("C") < order.index("B")


def test_nothing_to_reorder(organiser):
    tour = line_tour(organiser, ("A", 10.0, {}), ("B", 11.0, {}))
    assert suggest_order(tour.ordered_stops()) is None


def test_use_the_suggested_order(organiser):
    tour = line_tour(organiser, ("A", 10.0, {}), ("C", 12.0, {}), ("B", 11.0, {}), ("D", 13.0, {}))
    before = tour.distance_km
    client = login(organiser)
    html = client.get(reverse("tours:plan", args=[tour.slug]), {"order": 1}, HTTP_HX_REQUEST="true").content.decode()
    assert "Use this order" in html
    client.post(reverse("tours:plan_order", args=[tour.slug]))
    tour.refresh_from_db()
    assert tour.distance_km < before
    assert [stop.order for stop in tour.ordered_stops()] == [0, 1, 2, 3]


# ── Hints ───────────────────────────────────────────────────────────

def test_the_group_size_hint_only_for_tours_that_look_for_travellers(organiser, farm, village):
    looking = published(organiser, "Together", {"community": farm}, {"community": village})
    alone = published(organiser, "Alone", {"community": farm}, {"community": village}, open_to_join=False)
    group_hint = "3 to 5 people fit into a community most easily; with experience, up to 10."
    assert group_hint in hints(looking, looking.ordered_stops())
    assert group_hint not in hints(alone, alone.ordered_stops())


def test_the_week_tip_is_where_the_days_are_chosen(east, organiser):
    html = login(organiser).get(reverse("tours:plan", args=[east.slug])).content.decode()
    assert html.count("Hosts usually gain from help after about a week.") == 1


def test_the_hints_say_what_applies(organiser, farm):
    today = timezone.localdate()
    tour = published(organiser, "Short", {"community": farm, "arrive_on": today, "leave_on": today + timedelta(days=2)},
                     max_people=4)
    found = hints(tour, tour.ordered_stops())
    assert "Visit at least two communities so gifts can travel." in found


# ── Directions in a maps app, for those who travel along ────────────

def test_travellers_get_directions_to_each_stop(east, organiser, other):
    url = reverse("tours:detail", args=[east.slug])
    html = login(organiser).get(url).content.decode()
    village_link = f"geo:{round(VILLAGE_POINT.y, 6)},{round(VILLAGE_POINT.x, 6)}"
    assert village_link in html
    assert "maps.apple.com/?daddr=" in html
    assert f"openstreetmap.org/directions?engine=fossgis_osrm_car&amp;route=%3B{round(VILLAGE_POINT.y, 6)}" in html
    # The private farm only roughly: the group hasn't been taken in yet
    assert not exact(FARM_POINT, html)
    assert "approximate place until the host has agreed" in html

    for client in (login(other), login(person("Nobody"))):
        assert 'href="geo:' not in client.get(url).content.decode()
    from django.test import Client

    assert 'href="geo:' not in Client().get(url).content.decode()


def test_directions_use_the_exact_place_once_the_host_agreed(east, organiser, farm):
    from gift_economy.matches.models import Match

    from ..visits import ask_host

    stop = Stop.objects.get(tour=east, community=farm)
    match = ask_host(stop, organiser, message="Four of us, for a week")
    match.status = Match.STATUS_ACCEPTED
    match.save()
    html = login(organiser).get(reverse("tours:detail", args=[east.slug])).content.decode()
    assert f"geo:{round(FARM_POINT.y, 6)},{round(FARM_POINT.x, 6)}" in html


def test_the_pin_is_named_after_the_community_also_at_its_event(organiser, village):
    fest = Event.objects.create(community=village, title="Open day")
    tour = published(organiser, "Fest", {"event": fest}, {"name": "Harbour", "location": Point(8.8, 53.1, srid=4326)},
                     travel_mode="bicycle")
    html = login(organiser).get(reverse("tours:detail", args=[tour.slug])).content.decode()
    assert "(Elbtal)" in html and "(Open%20day)" not in html
    assert "(Harbour)" in html
    assert "engine=fossgis_osrm_bike" in html
    assert "google.com/maps/dir/?api=1&amp;destination=" in html and "travelmode=bicycling" in html
