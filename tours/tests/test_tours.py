import re
from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from communities.models import Community
from events.models import Event
from gift_economy.gifts.skills.models import Skill
from users.models import User

from ..models import Stop, Tour, append_stop, move_stop, remove_stop


def exact(point, text):
    """Whether `text` has a coordinate of `point` as it is, not just a number starting
    with the same digits (an approximate point nearby can: 13.06451…)."""
    return any(re.search(re.escape(str(value)) + r"(?!\d)", text) for value in (point.x, point.y))

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
    assert tour.title not in login(other).get(reverse("tours:api-list")).content.decode()


def test_only_the_organiser_edits(tour, organiser, other):
    for name in ("edit", "plan"):
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
    assert tour.title not in Client().get(reverse("tours:api-list")).content.decode()
    assert tour.title not in login(other).get(reverse("tours:api-list")).content.decode()
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


def test_the_list_shows_tours_then_ideas_and_filters_them(organiser, farm, village):
    today = timezone.localdate()
    dated = Tour.objects.create(title="Dated tour", organiser=organiser, published_at=timezone.now())
    add(dated, community=farm, arrive_on=today + timedelta(days=5))
    add(dated, community=village, arrive_on=today + timedelta(days=12))
    Tour.objects.create(title="Just an idea", organiser=organiser, published_at=timezone.now())
    over = Tour.objects.create(title="Long ago", organiser=organiser, published_at=timezone.now())
    add(over, community=farm, arrive_on=today - timedelta(days=40), leave_on=today - timedelta(days=30))

    both = Client().get(reverse("tours:api-list")).content.decode()
    assert both.index("Dated tour") < both.index("Just an idea") and "Long ago" not in both
    tours = Client().get(reverse("tours:api-list"), {"show": "tours"}).content.decode()
    assert "Dated tour" in tours and "Just an idea" not in tours
    ideas = Client().get(reverse("tours:api-list"), {"show": "ideas"}).content.decode()
    assert "Just an idea" in ideas and "Dated tour" not in ideas
    # The map follows the same filter
    assert slugs(routes(show="tours")) == {dated.slug}


def test_the_hosts_api_gives_rough_places_and_current_events(farm, project, village, other):
    response = login(other).get(reverse("tours:api-hosts"), {"q": "hof"}).json()
    assert [r["name"] for r in response["results"]] == ["Lindenhof"]
    assert response["results"][0]["place"] == "Potsdam, Deutschland"
    response = login(other).get(reverse("tours:api-hosts"), {"q": "elbtal"}).json()
    assert [e["title"] for e in response["results"][0]["events"]] == ["Rocket stove"]


def test_a_stop_needs_an_event_of_its_community(tour, organiser, farm, project):
    response = login(organiser).post(tour.url("plan"), {"where": "community", "community": farm.pk, "event": project.pk})
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
    assert response.url == tour.url("plan")
    assert tour.organiser == organiser and not tour.is_published

    client.post(tour.url("plan"), {
        "where": "place", "location_name": "Station square, Leipzig", "location": "SRID=4326;POINT (12.38 51.34)",
        "country": "DE", "arrive_on": today + timedelta(days=5),
    })
    client.post(tour.url("plan"), {
        "where": "community", "community": farm.pk, "arrive_on": today + timedelta(days=6),
        "leave_on": today + timedelta(days=13),
    })
    client.post(tour.url("plan"), {
        "where": "community", "community": project.community.pk, "event": project.pk,
        "arrive_on": today + timedelta(days=20), "leave_on": today + timedelta(days=30),
    })
    assert [s.label for s in tour.ordered_stops()] == ["Station square, Leipzig", "Lindenhof", "Rocket stove"]

    client.post(tour.url("publish"))
    tour.refresh_from_db()
    assert tour.is_published and tour.listed

    listed = login(other).get(reverse("tours:api-list")).content.decode()
    assert "Clay and seeds" in listed
    page = login(other).get(tour.get_absolute_url()).content.decode()
    for name in ("Station square, Leipzig", "Lindenhof", "Rocket stove", "Potsdam, Deutschland"):
        assert name in page
    # Nothing of the private farm's exact place
    assert "Lindenweg" not in page and "14467" not in page
    assert not exact(FARM_POINT, page)


# ── Package 2: the map ──────────────────────────────────────────────

def published(organiser, title, *stops, **fields):
    tour = Tour.objects.create(title=title, organiser=organiser, published_at=timezone.now(), **fields)
    for stop in stops:
        add(tour, **stop)
    return tour


def routes(client=None, **params):
    return (client or Client()).get(reverse("tours:api-routes"), params).json()["features"]


def slugs(features):
    return {f["properties"]["slug"] for f in features}


def test_routes_in_the_visible_area(organiser, farm, village):
    east = published(organiser, "East", {"community": farm}, {"community": village})
    west = published(organiser, "West", {"name": "Bordeaux", "location": Point(-0.57, 44.84, srid=4326)},
                     {"name": "Toulouse", "location": Point(1.44, 43.6, srid=4326)})
    Tour.objects.create(title="Draft", organiser=organiser)
    assert slugs(routes(bbox="12,50,15,53")) == {east.slug}
    assert slugs(routes(bbox="-2,42,3,46")) == {west.slug}
    assert slugs(routes()) == {east.slug, west.slug}


def test_a_tour_with_one_stop_is_found_by_its_stop(organiser, village):
    tour = published(organiser, "Just Dresden", {"community": village})
    assert slugs(routes(bbox="13,50,14,52")) == {tour.slug}
    assert routes(bbox="0,40,1,41") == []


def test_no_exact_private_place_in_any_payload(organiser, farm, village):
    tour = published(organiser, "East", {"community": farm}, {"community": village})
    payload = Client().get(reverse("tours:api-routes")).content.decode()
    assert not exact(FARM_POINT, payload)
    assert "Lindenweg" not in payload and "14467" not in payload
    stop = next(f for f in routes() if f["properties"]["kind"] == "stop" and f["properties"]["number"] == 1)
    assert stop["properties"]["rough"] is True
    assert Point(stop["geometry"]["coordinates"]).distance(farm.rough_place()[1]) < 1e-9
    page = Client().get(tour.get_absolute_url()).content.decode()
    assert not exact(FARM_POINT, page) and "Lindenweg" not in page


def test_filters_narrow_map_and_list(organiser, farm, village):
    today = timezone.localdate()
    clay, yoga = Skill.objects.create(name="Clay building"), Skill.objects.create(name="Yoga")
    soon = published(organiser, "Soon by bike", {"community": farm, "arrive_on": today + timedelta(days=5)},
                     {"community": village, "arrive_on": today + timedelta(days=9)}, travel_mode="bicycle", children_welcome=True)
    soon.learn_skills.add(clay)
    later = published(organiser, "Later by van", {"community": farm, "arrive_on": today + timedelta(days=90)},
                      {"community": village, "arrive_on": today + timedelta(days=99)})
    later.learn_skills.add(yoga)

    assert slugs(routes(mode="bicycle")) == {soon.slug}
    assert slugs(routes(children="1")) == {soon.slug}
    assert slugs(routes(learn="Yoga,Basket weaving")) == {later.slug}
    assert slugs(routes(**{"from": (today + timedelta(days=60)).isoformat()})) == {later.slug}
    assert slugs(routes(until=(today + timedelta(days=30)).isoformat())) == {soon.slug}
    listed = Client().get(reverse("tours:api-list"), {"mode": "bicycle"}).content.decode()
    assert "Soon by bike" in listed and "Later by van" not in listed


def test_near_a_place_sorts_the_list(organiser, farm, village):
    west = published(organiser, "West", {"name": "Bordeaux", "location": Point(-0.57, 44.84, srid=4326)},
                     {"name": "Toulouse", "location": Point(1.44, 43.6, srid=4326)}, starts_on=None)
    east = published(organiser, "East", {"community": farm}, {"community": village})
    # Both are tour ideas (no dates); near Dresden, East comes first, near Bordeaux, West
    html = Client().get(reverse("tours:api-list"), {"show": "ideas", "near": "51.05,13.74"}).content.decode()
    assert html.index("East") < html.index("West")
    html = Client().get(reverse("tours:api-list"), {"show": "ideas", "near": "44.84,-0.57"}).content.decode()
    assert html.index("West") < html.index("East")
    # It only sorts: the map still shows both
    assert slugs(routes(near="51.05,13.74")) == {east.slug, west.slug}


def test_search_finds_names_skills_stops_and_gifts(organiser, farm, village, project):
    from gift_economy.gifts.models import Listing
    clay = published(organiser, "Clay trip", {"community": farm})
    stove = published(organiser, "Second trip", {"event": project})
    yoga = published(organiser, "Third trip", {"name": "Station square, Leipzig", "location": Point(12.38, 51.34, srid=4326)})
    yoga.learn_skills.add(Skill.objects.create(name="Yoga"))
    Listing.objects.create(type=Listing.TYPE_OFFER, kind=Listing.KIND_MATERIAL, title="Lehm", community=farm)

    assert slugs(routes(q="clay trip")) == {clay.slug}
    assert slugs(routes(q="lehm")) == {clay.slug}          # an offer of a host on the way
    assert slugs(routes(q="rocket")) == {stove.slug}       # an event on the way
    assert slugs(routes(q="yoga")) == {yoga.slug}          # what it wants to learn
    assert slugs(routes(q="leipzig")) == {yoga.slug}       # another place on the way
    assert slugs(routes(q="lindenhof")) == {clay.slug}     # a community on the way
    assert routes(q="lindenweg") == []                     # never a private community's street
    suggested = Client().get(reverse("tours:api-suggest"), {"q": "yog"}).json()
    assert {"value": "Yoga", "type": "skill"} in suggested


def test_animals_welcome(organiser, farm, village):
    dog = published(organiser, "With the dog", {"community": farm}, {"community": village}, animals_welcome=True)
    published(organiser, "Without", {"community": farm}, {"community": village})
    assert slugs(routes(animals="1")) == {dog.slug}


def test_the_list_pages_stay_in_the_partial(organiser):
    for number in range(25):
        published(organiser, f"Idea {number}")
    html = Client().get(reverse("tours:api-list"), {"mode": "van"}).content.decode()
    assert f'href="{reverse("tours:api-list")}?mode=van&amp;page=2"' in html


def test_the_route_editor_lives_at_plan(tour, organiser):
    assert tour.url("plan").endswith(f"/community-tours/{tour.slug}/plan/")
    assert login(organiser).get(tour.url("plan")).status_code == 200


def test_a_card_opens_its_tour_as_a_page(organiser):
    tour = published(organiser, "An idea")
    html = Client().get(reverse("tours:api-list"), {"show": "ideas"}).content.decode()
    cards = html[html.index('data-tour='):]
    # Only the pages load into the list; a card's link is a plain link
    assert tour.get_absolute_url() in cards
    assert "hx-boost" not in cards[:cards.index(tour.get_absolute_url())]


# ── Pins ────────────────────────────────────────────────────────────

def test_stops_have_a_pin_by_what_they_are(organiser, farm, village, project):
    farm.type = Community.COMMUNITY_TYPE_FARM
    farm.save()
    published(organiser, "Pins", {"community": farm}, {"event": project},
              {"name": "Station square, Leipzig", "location": Point(12.38, 51.34, srid=4326)})
    pins = {f["properties"]["number"]: (f["properties"]["icon"], f["properties"]["color"])
            for f in routes() if f["properties"]["kind"] == "stop"}
    assert pins == {1: (0xF4D8, "#5A5527"), 2: (0xF85E, "#452912"), 3: (0xF3C5, "#da6137")}


def test_an_idea_without_stops_shows_about_where_its_organiser_lives(organiser, other):
    organiser.location = FARM_POINT
    organiser.location_name = "Lindenweg 7, 14467 Potsdam, Deutschland"
    organiser.save()
    idea = published(organiser, "Somewhere south")
    # Nobody logged in: no home on the map
    assert routes() == []
    client = login(other)
    features = client.get(reverse("tours:api-routes")).json()["features"]
    assert [f["properties"]["kind"] for f in features] == ["home"]
    home = features[0]
    assert home["properties"]["slug"] == idea.slug and home["properties"]["icon"] == 0xF207
    assert home["properties"]["place"] == "Potsdam, Deutschland"
    assert Point(home["geometry"]["coordinates"]) != Point(FARM_POINT.x, FARM_POINT.y)
    payload = client.get(reverse("tours:api-routes"), {"bbox": "12,51,14,53"}).content.decode()
    assert idea.slug in payload
    assert not exact(FARM_POINT, payload) and "Lindenweg" not in payload
    # An idea with stops shows its stops, not the home
    add(idea, name="Leipzig", location=Point(12.38, 51.34, srid=4326))
    kinds = [f["properties"]["kind"] for f in client.get(reverse("tours:api-routes")).json()["features"]]
    assert kinds == ["stop"]


def test_stops_link_to_their_community_or_event(organiser, farm, project):
    today = timezone.localdate()
    published(organiser, "Links", {"community": farm, "arrive_on": today + timedelta(days=3)}, {"event": project},
              {"name": "Leipzig", "location": Point(12.38, 51.34, srid=4326)})
    stops = {f["properties"]["number"]: f["properties"] for f in routes() if f["properties"]["kind"] == "stop"}
    assert stops[1]["link"] == farm.get_absolute_url() and stops[1]["stop_dates"]
    assert stops[2]["link"] == project.get_absolute_url()
    assert stops[3]["link"] == ""
    assert stops[1]["stop_image"] == "" and stops[3]["stop_image"] == ""


def test_the_map_tells_about_the_tour(organiser, other, farm, village):
    tour = published(organiser, "Told", {"community": farm, "onward_mode": "train"}, {"community": village},
                     {"name": "Leipzig", "location": Point(12.38, 51.34, srid=4326)},
                     travel_mode="bicycle", description="Lehm " * 100)
    tour.learn_skills.add(*(Skill.objects.create(name=name) for name in ("Yoga", "Clay", "Bees", "Bread", "Wool")))
    route = next(f["properties"] for f in routes() if f["properties"]["kind"] == "route")
    # A leg's travel mode is the stop's onward mode, else the tour's
    assert route["leg_modes"] == [0xF238, 0xF206]
    assert route["mode_icon"] == "fa-bicycle" and len(route["description"]) <= 160
    assert len(route["learn"]) == 4
    # The organiser's name only for people logged in, as on the tour's page
    assert route["organiser"] == ""
    route = next(f["properties"] for f in routes(login(other)) if f["properties"]["kind"] == "route")
    assert route["organiser"] == "Olga"


def test_the_tour_page_shows_who_travels_and_their_skills(organiser, other, village):
    from gift_economy.gifts.models import Listing
    from gift_economy.gifts.skills.models import get_or_create_skill
    tour = published(organiser, "With skills", {"community": village})
    Listing.objects.create(owner=organiser, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill=get_or_create_skill("Beekeeping")[0])
    hidden = Listing.objects.create(owner=organiser, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL,
                                    skill=get_or_create_skill("Juggling")[0], available=False)
    page = login(other).get(tour.get_absolute_url()).content.decode()
    assert "Who travels" in page and organiser.get_absolute_url() in page
    assert "Beekeeping" in page and hidden.skill.name not in page
    # Logged out: neither who travels nor their skills
    page = Client().get(tour.get_absolute_url()).content.decode()
    assert organiser.get_absolute_url() not in page and "Beekeeping" not in page


def test_cards_show_countries_and_the_organiser_to_people_logged_in(organiser, other, farm, village):
    published(organiser, "Card", {"community": farm}, {"community": village})
    html = login(other).get(reverse("tours:api-list")).content.decode()
    assert "Germany" in html or "Deutschland" in html
    assert organiser.get_absolute_url() in html
    assert organiser.get_absolute_url() not in Client().get(reverse("tours:api-list")).content.decode()
