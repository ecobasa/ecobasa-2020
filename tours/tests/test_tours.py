from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from communities.models import Community
from events.models import Event
from users.models import User

from ..models import Stop, Tour, append_stop, move_stop, remove_stop

pytestmark = pytest.mark.django_db

# Invented places: a private farm with a street address, a public ecovillage
FARM_POINT = Point(13.0645, 52.3989, srid=4326)
VILLAGE_POINT = Point(13.7373, 51.0504, srid=4326)


@pytest.fixture
def organiser():
    return User.objects.create_user(email="olga@example.com", password="secret", name="Olga")


@pytest.fixture
def other():
    return User.objects.create_user(email="otto@example.com", password="secret", name="Otto")


@pytest.fixture
def farm():
    ambassador = User.objects.create_user(email="amb@example.com", password="secret", name="Ana")
    return Community.objects.create(
        name="Lindenhof", owner=ambassador, location=FARM_POINT, country="DE",
        location_name="Lindenweg 7, 14467 Potsdam, Deutschland", location_public=False,
    )


@pytest.fixture
def village():
    return Community.objects.create(
        name="Elbtal", location=VILLAGE_POINT, country="DE", location_name="Dresden, Deutschland",
        location_public=True,
    )


@pytest.fixture
def project(village):
    today = timezone.localdate()
    return Event.objects.create(
        community=village, title="Rocket stove", starts_on=today + timedelta(days=20), ends_on=today + timedelta(days=40),
    )


@pytest.fixture
def tour(organiser):
    return Tour.objects.create(title="Clay and seeds", organiser=organiser)


def login(user):
    client = Client()
    client.force_login(user)
    return client


def add(tour, **fields):
    stop = Stop(tour=tour, **fields)
    append_stop(stop)
    return stop


# ── The route ───────────────────────────────────────────────────────

def test_route_goes_through_the_rough_place_of_a_private_community(tour, farm, village):
    add(tour, community=farm)
    add(tour, community=village)
    tour.refresh_from_db()

    rough = farm.rough_place()[1]
    first = Point(tour.route.coords[0], srid=4326)
    assert first.distance(rough) < 1e-9
    assert first.distance(FARM_POINT) > 1e-6
    assert Point(tour.route.coords[1]).distance(VILLAGE_POINT) < 1e-9
    # Straight distance Potsdam–Dresden is about 150 km; on roads about 1.3 times that
    assert 170 < tour.distance_km < 230


def test_route_follows_when_a_community_makes_its_place_public(tour, farm, village):
    add(tour, community=farm)
    add(tour, community=village)
    farm.location_public = True
    farm.save()
    tour.refresh_from_db()
    assert Point(tour.route.coords[0]).distance(FARM_POINT) < 1e-9


def test_dates_and_countries_come_from_the_stops(tour, farm, project):
    today = timezone.localdate()
    tour.countries = ["FR"]
    tour.save()
    add(tour, community=farm, arrive_on=today + timedelta(days=3), leave_on=today + timedelta(days=17))
    add(tour, event=project, arrive_on=today + timedelta(days=20), leave_on=today + timedelta(days=30))
    add(tour, name="Ferry port", location=Point(10.0, 54.3, srid=4326), country="DK", leave_on=today + timedelta(days=31))
    tour.refresh_from_db()

    assert tour.starts_on == today + timedelta(days=3)
    assert tour.ends_on == today + timedelta(days=31)
    assert [c.code for c in tour.countries] == ["DE", "DK"]
    assert not tour.is_idea
    assert tour.is_upcoming


def test_a_tour_without_stops_is_an_idea_and_keeps_its_countries(tour):
    tour.countries = ["PT", "ES"]
    tour.save()
    tour.rebuild_route()
    tour.refresh_from_db()
    assert tour.is_idea
    assert [c.code for c in tour.countries] == ["PT", "ES"]
    assert tour.route is None


def test_a_stop_at_an_event_is_at_its_community(tour, project, village):
    stop = add(tour, event=project)
    assert stop.community == village
    assert stop.host == project
    assert stop.public_place() == village.rough_place()


def test_order_is_kept_when_moving_and_removing(tour, farm, village):
    a = add(tour, community=farm)
    b = add(tour, community=village)
    c = add(tour, name="Meeting point", location=Point(12.0, 51.0, srid=4326))
    assert [s.pk for s in tour.ordered_stops()] == [a.pk, b.pk, c.pk]

    move_stop(c, -1)
    assert [s.pk for s in tour.ordered_stops()] == [a.pk, c.pk, b.pk]
    move_stop(a, -1)  # already first: stays
    assert [s.pk for s in tour.ordered_stops()] == [a.pk, c.pk, b.pk]

    remove_stop(Stop.objects.get(pk=c.pk))
    assert [(s.pk, s.order) for s in tour.ordered_stops()] == [(a.pk, 0), (b.pk, 1)]


def test_move_through_the_view(tour, farm, village, organiser):
    a = add(tour, community=farm)
    b = add(tour, community=village)
    response = login(organiser).post(reverse("tours:stop_move", args=[tour.slug, b.pk, "up"]))
    assert response.status_code == 302
    assert [s.pk for s in tour.ordered_stops()] == [b.pk, a.pk]


# ── Who sees and edits what ─────────────────────────────────────────

def test_a_draft_is_only_for_its_organiser(tour, organiser, other):
    url = tour.get_absolute_url()
    assert login(organiser).get(url).status_code == 200
    assert login(other).get(url).status_code == 404
    assert Client().get(url).status_code == 404
    assert tour.title not in login(other).get(reverse("tours:list")).content.decode()


def test_only_the_organiser_edits(tour, organiser, other):
    for name in ("edit", "stops"):
        assert login(other).get(tour.url(name)).status_code == 403
        assert login(organiser).get(tour.url(name)).status_code == 200
    assert login(other).post(tour.url("publish")).status_code == 403
    tour.refresh_from_db()
    assert not tour.is_published


def test_a_personal_tour_that_is_not_listed_is_in_no_list(organiser, other):
    tour = Tour.objects.create(
        title="My own learning trip", organiser=organiser, open_to_join=False, listed=False,
        published_at=timezone.now(),
    )
    assert tour.title not in Client().get(reverse("tours:list")).content.decode()
    assert tour.title not in login(other).get(reverse("tours:list")).content.decode()
    assert tour not in Tour.objects.listed()
    assert login(other).get(tour.get_absolute_url()).status_code == 404
    staff = User.objects.create_user(email="staff@example.com", password="secret", name="Sam", is_staff=True)
    assert login(staff).get(tour.get_absolute_url()).status_code == 200
    # Its traveller finds it on the list page among their own
    assert tour.title in login(organiser).get(reverse("tours:list")).content.decode()


def test_a_tour_that_looks_for_travellers_is_always_listed(organiser):
    tour = Tour.objects.create(title="Van tour", organiser=organiser, open_to_join=True, listed=False)
    assert tour.listed


def test_a_personal_tour_is_hidden_by_default(organiser):
    response = login(organiser).post(reverse("tours:create"), {"title": "Alone", "travel_mode": "bicycle"})
    assert response.status_code == 302
    tour = Tour.objects.get(title="Alone")
    assert not tour.open_to_join
    assert not tour.listed


def test_the_list_splits_tours_and_ideas(organiser, farm, village):
    today = timezone.localdate()
    dated = Tour.objects.create(title="Dated tour", organiser=organiser, published_at=timezone.now())
    add(dated, community=farm, arrive_on=today + timedelta(days=5))
    add(dated, community=village, arrive_on=today + timedelta(days=12))
    Tour.objects.create(title="Just an idea", organiser=organiser, published_at=timezone.now())
    over = Tour.objects.create(title="Long ago", organiser=organiser, published_at=timezone.now())
    add(over, community=farm, arrive_on=today - timedelta(days=40), leave_on=today - timedelta(days=30))

    tours = Client().get(reverse("tours:list")).content.decode()
    assert "Dated tour" in tours and "Just an idea" not in tours and "Long ago" not in tours
    ideas = Client().get(reverse("tours:list") + "?tab=ideas").content.decode()
    assert "Just an idea" in ideas and "Dated tour" not in ideas


def test_the_hosts_api_gives_rough_places_and_current_events(farm, project, village, other):
    response = login(other).get(reverse("tours:api-hosts"), {"q": "hof"}).json()
    assert [r["name"] for r in response["results"]] == ["Lindenhof"]
    assert response["results"][0]["place"] == "Potsdam, Deutschland"
    response = login(other).get(reverse("tours:api-hosts"), {"q": "elbtal"}).json()
    assert [e["title"] for e in response["results"][0]["events"]] == ["Rocket stove"]


def test_a_stop_needs_an_event_of_its_community(tour, organiser, farm, project):
    response = login(organiser).post(tour.url("stops"), {"where": "community", "community": farm.pk, "event": project.pk})
    assert response.status_code == 200
    assert not tour.stops.exists()


# ── Done when (docs/community-tours-plan.md, package 1) ──────────────

def test_plan_publish_and_read_a_tour(organiser, other, farm, project):
    today = timezone.localdate()
    client = login(organiser)
    response = client.post(reverse("tours:create"), {
        "title": "Clay and seeds", "description": "Building with clay on the way.", "travel_mode": "van",
        "open_to_join": "on", "max_people": 4, "learn_skills": "",
    })
    tour = Tour.objects.get(title="Clay and seeds")
    assert response.url == tour.url("stops")
    assert tour.organiser == organiser and not tour.is_published

    client.post(tour.url("stops"), {
        "where": "place", "location_name": "Station square, Leipzig", "location": "SRID=4326;POINT (12.38 51.34)",
        "country": "DE", "arrive_on": today + timedelta(days=5),
    })
    client.post(tour.url("stops"), {
        "where": "community", "community": farm.pk, "arrive_on": today + timedelta(days=6),
        "leave_on": today + timedelta(days=13),
    })
    client.post(tour.url("stops"), {
        "where": "community", "community": project.community.pk, "event": project.pk,
        "arrive_on": today + timedelta(days=20), "leave_on": today + timedelta(days=30),
    })
    assert [s.label for s in tour.ordered_stops()] == ["Station square, Leipzig", "Lindenhof", "Rocket stove"]

    client.post(tour.url("publish"))
    tour.refresh_from_db()
    assert tour.is_published and tour.listed

    listed = login(other).get(reverse("tours:list")).content.decode()
    assert "Clay and seeds" in listed
    page = login(other).get(tour.get_absolute_url()).content.decode()
    for name in ("Station square, Leipzig", "Lindenhof", "Rocket stove", "Potsdam, Deutschland"):
        assert name in page
    # Nothing of the private farm's exact place
    assert "Lindenweg" not in page and "14467" not in page
    assert str(FARM_POINT.x) not in page and str(FARM_POINT.y) not in page
