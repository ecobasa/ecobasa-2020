import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from gift_economy.gifts import units
from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import get_or_create_skill
from gift_economy.gifts.testing import need as event_need, skill_offer, skill_wish
from gift_economy.matches.matching import match, side_of
from gift_economy.matches.models import Suggestion
from users.models import User

from .. import matching
from ..models import Vehicle
from .test_joining import accept, four_stops, person  # noqa: F401
from .test_tours import farm, login, organiser, other, project, published, village  # noqa: F401

pytestmark = pytest.mark.django_db

# Invented places: halfway between the farm near Potsdam and the village near Dresden, about
# 75 km from either, but right on the line between them; and Munich, far from it
ON_THE_WAY = Point(13.40, 51.75, srid=4326)
FAR_AWAY = Point(11.58, 48.14, srid=4326)


@pytest.fixture
def carpentry():
    return get_or_create_skill("Carpentry")[0]


@pytest.fixture
def east(organiser, farm, village):
    organiser.match_radius = 30
    organiser.save()
    return published(organiser, "Clay and seeds", {"community": farm}, {"community": village}, max_people=6)


def tour_need(tour, skill=None, **fields):
    fields.setdefault("kind", Listing.KIND_HANDS)
    return Listing.objects.create(type=Listing.TYPE_WISH, skill=skill, tour=tour, **fields)


def carpenter(name, point, radius=30):
    user = User.objects.create_user(email=f"{name.lower()}@example.com", password="secret", name=name,
                                    location=point, match_radius=radius)
    return user


# ── A need belongs to the tour ─────────────────────────────────────

def test_a_need_is_the_tours_and_answered_by_its_organiser(east, organiser, carpentry):
    need = tour_need(east, carpentry)
    assert need.owner is None and need.community is None
    assert need.holder == east and need.manager == organiser
    assert need.is_managed_by(organiser)
    assert need.get_absolute_url() == reverse("gifts:detail", args=[need.pk])
    # Not one of the organiser's own wishes
    assert need not in Listing.objects.of(organiser)
    assert need in Listing.objects.managed_by(organiser)


def test_a_need_doesnt_clash_with_the_organisers_own_wish_to_learn_it(east, organiser, carpentry):
    skill_wish(organiser, carpentry)
    skill_offer(organiser, carpentry)
    tour_need(east, carpentry, kind=Listing.KIND_SKILL)
    tour_need(published(organiser, "Second tour"), carpentry, kind=Listing.KIND_SKILL)
    assert Listing.objects.filter(skill=carpentry).count() == 4


def test_needs_of_drafts_and_personal_tours_are_matched_with_nobody(organiser, carpentry):
    from ..models import Tour

    draft = Tour.objects.create(title="Draft", organiser=organiser)
    personal = published(organiser, "Just me", open_to_join=False, listed=False)
    for tour in (draft, personal):
        need = tour_need(tour, carpentry)
        assert side_of(need) is None
        assert need not in Listing.objects.current()


# ── Found along the route ──────────────────────────────────────────

def test_someone_near_the_route_hears_of_the_need_and_someone_far_away_doesnt(east, organiser, carpentry):
    near, far = carpenter("Nora", ON_THE_WAY), carpenter("Fritz", FAR_AWAY)
    skill_offer(near, carpentry)
    skill_offer(far, carpentry)
    need = tour_need(east, carpentry, quantity=2, unit=units.PEOPLE)

    match(need, notify=False)

    found = Suggestion.objects.filter(user=near)
    assert found.count() == 1
    suggestion = found.get()
    assert suggestion.distance_km is not None and suggestion.distance_km < 10
    assert suggestion.text == "The tour Clay and seeds is looking for: Carpentry (2 people)"
    assert suggestion.action_url == f"{east.url('join')}?need={need.pk}"
    # The organiser hears of her, not of him: he is far from the route. Point to point,
    # Nora would be too far from either stop (about 75 km)
    assert set(Suggestion.objects.filter(user=organiser).values_list("other_user__name", flat=True)) == {"Nora"}
    assert Suggestion.objects.get(user=organiser).own_text == "your tour Clay and seeds: Carpentry"
    assert not Suggestion.objects.filter(user=far).exists()


def test_a_need_is_matched_again_when_the_route_changes(east, organiser, carpentry, django_capture_on_commit_callbacks):
    from ..models import Stop, append_stop

    munich_carpenter = carpenter("Mia", Point(11.60, 48.15, srid=4326))
    skill_offer(munich_carpenter, carpentry)
    with django_capture_on_commit_callbacks(execute=True):
        tour_need(east, carpentry)
    assert not Suggestion.objects.filter(user=munich_carpenter).exists()

    with django_capture_on_commit_callbacks(execute=True):
        append_stop(Stop(tour=east, name="Munich", location=FAR_AWAY.clone()))
    assert Suggestion.objects.filter(user=munich_carpenter).exists()


# ── Covered by who joins ───────────────────────────────────────────

def test_a_need_for_two_is_half_covered_after_one_joins(four_stops, organiser, other, carpentry):
    need = tour_need(four_stops, carpentry, quantity=2, unit=units.PEOPLE)
    stops = four_stops.ordered_stops()
    page = login(other).get(f"{reverse('tours:join', args=[four_stops.slug])}?need={need.pk}").content.decode()
    assert "You could cover" in page

    login(other).post(reverse("tours:join", args=[four_stops.slug]), {
        "from_stop": stops[0].pk, "to_stop": stops[2].pk, "people": 1, "message": "I bring my tools",
        f"need_{need.pk}": "on", f"quantity_{need.pk}": 1,
    })
    traveller = four_stops.travellers.get(user=other)
    assert [(c.listing, c.quantity) for c in traveller.match.contributions.all()] == [(need, 1)]
    assert need.status == Listing.STATUS_OFFERED

    accept(traveller.match, organiser)
    need = Listing.objects.get(pk=need.pk)
    assert need.promised_quantity == 1 and need.remaining == 1 and not need.is_done
    assert need.progress == "1 of 2 people promised"
    # The second carpenter works alongside the first
    assert matching.role(need, four_stops.team_skill_ids()) == matching.ALONGSIDE


def test_completes_the_team_until_someone_on_it_can(east, organiser, carpentry):
    need = tour_need(east, carpentry)
    assert matching.role(need, east.team_skill_ids()) == matching.COMPLETES
    skill_offer(organiser, carpentry)
    assert matching.role(need, east.team_skill_ids()) == matching.ALONGSIDE


# ── Vehicles give the places ───────────────────────────────────────

def test_room_on_a_leg_comes_from_its_vehicles(four_stops, organiser):
    stops = four_stops.ordered_stops()
    four_stops.max_people = 10
    four_stops.save()
    Vehicle.objects.create(tour=four_stops, label="Blue van", seats=2).drivers.add(organiser)
    Vehicle.objects.create(tour=four_stops, label="Trailer bus", seats=3, from_stop=stops[1], to_stop=stops[2])
    assert four_stops.room() == [3, 6, 3]
    # The organiser travels on all of them
    assert four_stops.free_places() == [2, 5, 2]
    # The group size still caps it
    four_stops.max_people = 4
    four_stops.save()
    assert four_stops.room() == [3, 4, 3]


def test_without_vehicles_or_group_size_there_is_no_limit(organiser, other, farm, village):
    tour = published(organiser, "Open road", {"community": farm}, {"community": village})
    assert tour.free_places() == [None]
    assert tour.fits(None, None, 20)
    Vehicle.objects.create(tour=tour, label="Car", seats=3).drivers.add(organiser, other)
    # Two drivers, one driver's seat: the other sits in one of the three seats
    assert tour.free_places() == [3]


# ── The page for vehicles and needs ────────────────────────────────

def _management(prefix, total, initial=0):
    return {f"{prefix}-TOTAL_FORMS": total, f"{prefix}-INITIAL_FORMS": initial,
            f"{prefix}-MIN_NUM_FORMS": 0, f"{prefix}-MAX_NUM_FORMS": 1000}


def test_organisers_add_a_vehicle_and_a_need(east, organiser, other):
    url = reverse("tours:needs", args=[east.slug])
    assert login(other).get(url).status_code == 403
    assert login(organiser).get(url).status_code == 200
    response = login(organiser).post(url, {
        **_management("vehicles", 1), **_management("needs", 1),
        "vehicles-0-label": "Blue van", "vehicles-0-drivers": [organiser.pk], "vehicles-0-seats": 4,
        "vehicles-0-note": "Roof rack",
        "needs-0-kind": Listing.KIND_HANDS, "needs-0-title": "Someone who can cook", "needs-0-quantity": 1,
    })
    assert response.status_code == 302
    vehicle = east.vehicles.get()
    assert (vehicle.label, vehicle.places, vehicle.note) == ("Blue van", 5, "Roof rack")
    need = east.listings.get()
    assert need.is_wish and need.tour == east and need.owner is None

    page = login(other).get(east.get_absolute_url()).content.decode()
    assert "re still looking for" in page and "Someone who can cook" in page
    assert "Completes the team" in page and "Blue van" in page


def test_skills_the_hosts_look_for_are_offered_as_needs(east, organiser, project, carpentry):
    from ..models import Stop, append_stop

    append_stop(Stop(tour=east, event=project))
    event_need(project, "Carpentry", skill=carpentry)
    clay = get_or_create_skill("Clay building")[0]
    skill_wish(east.ordered_stops()[0].community, clay)

    gaps = dict(matching.gaps(east))
    assert set(gaps) == {carpentry, clay}
    assert gaps[carpentry] == ["Rocket stove"] and gaps[clay] == ["Lindenhof"]

    # Nobody needs to look for what someone on the tour can
    skill_offer(organiser, clay)
    assert set(dict(matching.gaps(east))) == {carpentry}

    login(organiser).post(reverse("tours:needs_add", args=[east.slug]), {"skill": carpentry.pk})
    need = east.listings.get()
    assert need.skill == carpentry and need.kind == Listing.KIND_HANDS
    assert matching.gaps(east) == []


# ── In the gifts list and on its map ───────────────────────────────

def test_a_tours_need_is_in_the_gifts_list_and_map_at_the_start_of_its_route(east, organiser, other, farm, carpentry):
    need = tour_need(east, carpentry)
    from ..models import Tour

    hidden = tour_need(Tour.objects.create(title="Draft", organiser=organiser), carpentry)

    features = login(other).get(reverse("gifts:api-markers"), {"bbox": "5,45,20,56"}).json()["features"]
    ours = [f for f in features if f["properties"]["tour"] == "Clay and seeds"]
    assert len(ours) == 1 and ours[0]["properties"]["url"] == need.get_absolute_url()
    # At the farm's rough place, where the route starts, never its door
    start = Point(ours[0]["geometry"]["coordinates"], srid=4326)
    assert start.distance(farm.rough_place()[1]) < 1e-9
    assert not any(f["properties"]["title"] == hidden.display_title and f["properties"]["tour"] == "Draft" for f in features)

    page = login(other).get(reverse("gifts:api-list"), {"search": "Clay and seeds"}).content.decode()
    assert "Carpentry" in page and "Clay and seeds" in page
    assert "Carpentry" in login(other).get(reverse("gifts:api-list"), {"country": "DE", "search": "Clay"}).content.decode()
    assert "Carpentry" not in login(other).get(reverse("gifts:api-list"), {"country": "FR", "search": "Clay"}).content.decode()
    # The organiser doesn't see the tour's own needs in the list, as with their own
    assert "Carpentry" not in login(organiser).get(reverse("gifts:api-list"), {"search": "Clay"}).content.decode()
    # Its own gift page: join and cover it, or give or lend it without travelling
    page = login(other).get(need.get_absolute_url()).content.decode()
    assert f"{east.url('join')}?need={need.pk}" in page
    assert "Offer to fulfill this wish" in page and "Clay and seeds" in page


def test_someone_lends_a_van_to_the_tour_without_travelling(east, organiser, other):
    from gift_economy.matches.models import Match

    van = tour_need(east, kind=Listing.KIND_VEHICLE, title="Van")
    login(other).post(van.get_absolute_url(), {"message": "Take my van, I stay home", "location_type": Match.LOC_YOUR_PLACE})
    match = Match.objects.get(from_user=other)
    assert match.target == van and match.recipient == organiser
    assert match.get_absolute_url()
    assert login(organiser).get(match.get_absolute_url()).status_code == 200


def test_without_a_picture_the_tour_shows_its_first_vehicles(east, other):
    from django.core.files.uploadedfile import SimpleUploadedFile

    gif = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"
    assert east.header_image == ""
    Vehicle.objects.create(tour=east, label="Old bus", seats=8)
    Vehicle.objects.create(tour=east, label="Blue van", seats=2, image=SimpleUploadedFile("van.gif", gif, "image/gif"))
    url = Vehicle.objects.get(label="Blue van").image.url
    assert east.header_image == url and east.picture == url
    assert url in login(other).get(east.get_absolute_url()).content.decode()


def test_a_need_of_a_tour_with_one_stop_is_on_the_map_too(organiser, other, village, carpentry):
    single = published(organiser, "Just to Elbtal", {"community": village})
    tour_need(single, carpentry)
    features = login(other).get(reverse("gifts:api-markers"), {"bbox": "5,45,20,56"}).json()["features"]
    ours = [f for f in features if f["properties"]["tour"] == "Just to Elbtal"]
    assert len(ours) == 1
    assert Point(ours[0]["geometry"]["coordinates"], srid=4326).distance(village.location) < 1e-9


def test_the_givers_name_on_the_map_links_to_them(other):
    from django.contrib.gis.geos import Point as P

    giver = carpenter("Gita", P(13.0, 52.0, srid=4326))
    Listing.objects.create(type=Listing.TYPE_OFFER, kind=Listing.KIND_TOOL, title="Ladder", owner=giver)
    features = login(other).get(reverse("gifts:api-markers"), {"bbox": "5,45,20,56"}).json()["features"]
    ladder = next(f["properties"] for f in features if f["properties"]["title"] == "Ladder")
    assert ladder["user_name"] == "Gita" and ladder["user_url"] == giver.get_absolute_url()


def test_a_need_of_a_tour_idea_without_stops_is_about_where_its_organiser_lives(organiser, other):
    from users.places import approximate

    organiser.location, organiser.location_name = Point(13.40, 52.52, srid=4326), "Kastanienallee 1, Berlin, Deutschland"
    organiser.save()
    idea = published(organiser, "Someday by van")
    van = tour_need(idea, kind=Listing.KIND_VEHICLE, title="Van")
    assert van.public_place[0] == "Berlin, Deutschland"
    features = login(other).get(reverse("gifts:api-markers"), {"bbox": "5,45,20,56"}).json()["features"]
    ours = [f for f in features if f["properties"]["tour"] == "Someday by van"]
    assert len(ours) == 1
    spot = Point(ours[0]["geometry"]["coordinates"], srid=4326)
    # Roughly, never the door
    assert 0 < spot.distance(organiser.location) < 0.2
    assert van.point == organiser.location and van.public_place[1] == approximate(organiser.location, organiser.pk)


def test_a_needs_gift_page_shows_the_tour_and_its_route(east, organiser, other, carpentry, farm):
    from .test_tours import FARM_POINT, exact

    need = tour_need(east, carpentry)
    html = login(other).get(reverse("gifts:detail", args=[need.pk])).content.decode()
    # What it is, who travels, where it goes
    assert "fa-route mr-1\"></i>Tour</span>" in html
    assert "1 person travels" in html and "5 places free" in html
    assert "Lindenhof" in html and "Elbtal" in html
    assert "Olga" in html
    # The whole route on the map, the private farm only roughly
    assert 'id="tour-route"' in html and '"kind": "route"' in html
    assert not exact(FARM_POINT, html)
    # Logged out: no organiser
    from django.test import Client

    assert "Olga" not in Client().get(reverse("gifts:detail", args=[need.pk])).content.decode()
