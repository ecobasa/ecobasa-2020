from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import get_or_create_skill
from gift_economy.gifts.testing import skill_offer, skill_wish
from gift_economy.matches.emails import send_suggestion_email
from gift_economy.matches.models import Match, StayDetails, Suggestion
from users.models import User

from .. import matching
from ..models import Tour
from .test_joining import person
from .test_needs import FAR_AWAY, ON_THE_WAY, tour_need
from .test_tours import farm, login, organiser, other, project, published, village  # noqa: F401

pytestmark = pytest.mark.django_db

# Invented: a town near the farm, a few km from Potsdam
NEAR_FARM = Point(13.10, 52.38, srid=4326)


def day(n):
    return timezone.localdate() + timedelta(days=n)


def aware(d):
    return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))


@pytest.fixture
def east(organiser, farm, village):
    """From the farm near Potsdam to the village near Dresden, in a week."""
    village.owner = person("Vera")
    village.save()
    return published(
        organiser, "Clay and seeds",
        {"name": "Berlin Hbf", "location": Point(13.369, 52.525, srid=4326), "leave_on": day(5)},
        {"community": farm, "arrive_on": day(5), "leave_on": day(6)},
        {"community": village, "arrive_on": day(8), "leave_on": day(12)},
        max_people=4,
    )


def stay(user, target, first, last, status=Match.STATUS_ACCEPTED, people=1):
    match = Match(from_user=user, recipient=target.get_match_owner(), message="Hi", status=status)
    match.target = target
    match.save()
    StayDetails.objects.create(match=match, stay_from=aware(first), stay_to=aware(last), people=people)
    return match


def tour_suggestions(user):
    return list(user.suggestions.filter(kind=Suggestion.KIND_TOURS))


# ── Why a tour fits ─────────────────────────────────────────────────

def test_a_stay_at_a_stop_around_its_days_with_the_stretch_from_the_nearest_stop(east, village):
    lena = User.objects.create_user(email="lena@example.com", password="secret", name="Lena", location=NEAR_FARM)
    match = stay(lena, village, day(9), day(16))
    matching.suggest_tour(east)

    [suggestion] = tour_suggestions(lena)
    assert suggestion.reason == Suggestion.REASON_STAY and suggestion.own == match and suggestion.other == east
    assert suggestion.text == "The tour Clay and seeds goes to Elbtal around the days that you are also there"
    assert suggestion.own_text == "your stay at Elbtal"
    # She gets on at the farm, the stop nearest her, and off where she stays
    stops = east.ordered_stops()
    assert suggestion.action_url == f"{east.url('join')}?from={stops[1].pk}&to={stops[2].pk}&suggestion={suggestion.pk}"
    page = login(lena).get(suggestion.action_url).content.decode()
    assert f'value="{stops[1].pk}" selected' in page and f'value="{stops[2].pk}" selected' in page
    # The request is written already
    assert f"I&#x27;m staying at Elbtal from {day(9):%B} {day(9).day} " in page
    assert "would like to travel there with you from Lindenhof." in page


def test_a_stay_in_other_weeks_or_without_room_fits_no_tour(east, village):
    later = person("Lars")
    stay(later, village, day(30), day(40))
    crowd = person("Carla")
    stay(crowd, village, day(9), day(10), people=4)
    matching.suggest_tour(east)
    assert tour_suggestions(later) == [] and tour_suggestions(crowd) == []


def test_a_stay_at_an_event_fits_a_stop_at_its_community(organiser, village, project):
    village.owner = person("Vera")
    village.save()
    tour = published(
        organiser, "To the stove", {"name": "Leipzig", "location": Point(12.37, 51.34, srid=4326), "leave_on": day(19)},
        {"community": village, "arrive_on": day(20), "leave_on": day(22)},
    )
    rosa = person("Rosa")
    stay(rosa, project, day(21), day(30), status=Match.STATUS_PENDING)
    matching.suggest_tour(tour)
    assert [s.other for s in tour_suggestions(rosa)] == [tour]


def test_a_tour_passing_near_where_one_lives(east):
    near = User.objects.create_user(email="nina@example.com", password="secret", name="Nina",
                                    location=ON_THE_WAY, match_radius=30)
    far = User.objects.create_user(email="fritz@example.com", password="secret", name="Fritz",
                                   location=FAR_AWAY, match_radius=30)
    matching.suggest_tour(east)
    [suggestion] = tour_suggestions(near)
    assert suggestion.reason == Suggestion.REASON_ROUTE and suggestion.own == near
    assert suggestion.text == "The tour Clay and seeds passes near you"
    assert suggestion.own_text == "where you live" and suggestion.distance_km < 30
    assert tour_suggestions(far) == []


def test_a_tour_that_wants_to_learn_what_one_wishes_to(east):
    permaculture = get_or_create_skill("Permaculture")[0]
    east.learn_skills.add(permaculture)
    pia = person("Pia")  # no place: she looks anywhere
    wish = skill_wish(pia, permaculture)
    matching.suggest_tour(east)
    [suggestion] = tour_suggestions(pia)
    assert suggestion.reason == Suggestion.REASON_LEARN and suggestion.own == wish
    assert suggestion.text == "The tour Clay and seeds wants to learn Permaculture too"
    assert suggestion.own_text == "your wish to learn: Permaculture"
    assert suggestion.action_url == f"{east.url('join')}?suggestion={suggestion.pk}"
    page = login(pia).get(suggestion.action_url).content.decode()
    assert "I&#x27;d like to learn Permaculture too and would love to learn it together." in page


def test_one_suggestion_per_tour_by_its_first_reason(east, village):
    permaculture = get_or_create_skill("Permaculture")[0]
    east.learn_skills.add(permaculture)
    lena = User.objects.create_user(email="lena@example.com", password="secret", name="Lena",
                                    location=ON_THE_WAY, match_radius=30)
    skill_wish(lena, permaculture)
    stay(lena, village, day(9), day(16))
    matching.suggest_tour(east)
    matching.suggest_for(lena)
    assert [s.reason for s in tour_suggestions(lena)] == [Suggestion.REASON_STAY]


# ── Who is not told ─────────────────────────────────────────────────

def test_no_suggestion_of_ones_own_tour(east, organiser, village):
    organiser.location = ON_THE_WAY
    organiser.save()
    stay(organiser, village, day(9), day(10))
    matching.suggest_tour(east)
    assert tour_suggestions(organiser) == []


def test_none_for_a_personal_tour_that_is_not_listed(organiser, village):
    village.owner = person("Vera")
    village.save()
    personal = published(
        organiser, "Just me", {"community": village, "arrive_on": day(8), "leave_on": day(9)},
        {"name": "Prague", "location": Point(14.42, 50.08, srid=4326), "arrive_on": day(10)},
        open_to_join=False, listed=False,
    )
    lena = person("Lena")
    stay(lena, village, day(8), day(9))
    assert matching.suggest_tour(personal) == []
    assert matching.suggest_for(lena) == []


def test_joining_or_withdrawing_the_stay_takes_it_back(east, village, django_capture_on_commit_callbacks):
    lena = person("Lena")
    with django_capture_on_commit_callbacks(execute=True):
        match = stay(lena, village, day(9), day(16))
    assert len(tour_suggestions(lena)) == 1

    match.status = Match.STATUS_WITHDRAWN
    match.save()
    assert tour_suggestions(lena) == []

    otto = person("Toni")
    with django_capture_on_commit_callbacks(execute=True):
        stay(otto, village, day(9), day(16))
    stops = east.ordered_stops()
    login(otto).post(reverse("tours:join", args=[east.slug]), {
        "from_stop": stops[0].pk, "to_stop": stops[2].pk, "people": 1, "message": "Hello",
    })
    assert tour_suggestions(otto) == []


def test_a_hidden_tour_isnt_suggested_again(east, village):
    lena = person("Lena")
    stay(lena, village, day(9), day(16))
    matching.suggest_tour(east)
    Suggestion.objects.update(dismissed_at=timezone.now())
    east.save()
    matching.suggest_tour(east)
    assert Suggestion.objects.filter(user=lena).count() == 1


def test_an_archived_tour_is_no_longer_suggested(east, village):
    lena = person("Lena")
    stay(lena, village, day(9), day(16))
    matching.suggest_tour(east)
    east.archived_at = timezone.now()
    east.save()
    matching.suggest_tour(east)
    assert tour_suggestions(lena) == []


# ── Where people see them ───────────────────────────────────────────

def test_shown_in_the_matches_list_and_the_weekly_email(east, village):
    lena = person("Lena")
    stay(lena, village, day(9), day(16))
    matching.suggest_tour(east)
    page = login(lena).get(reverse("matches:list")).content.decode()
    assert "Clay and seeds" in page and "Ask to join" in page

    mail.outbox.clear()
    assert send_suggestion_email(lena)
    body = mail.outbox[0].body
    assert "Tours for you" in body and "The tour Clay and seeds goes to Elbtal around the days that you are also there" in body
    assert east.url("join") in body


def test_the_stay_page_lists_tours_going_there(east, village):
    lena = User.objects.create_user(email="lena@example.com", password="secret", name="Lena", location=NEAR_FARM)
    match = stay(lena, village, day(9), day(16))
    page = login(lena).get(match.get_absolute_url()).content.decode()
    assert "Tours going there around your days" in page and "Clay and seeds" in page
    stops = east.ordered_stops()
    assert f"?from={stops[1].pk}&amp;to={stops[2].pk}" in page
    # Not for the host
    assert "Tours going there" not in login(village.owner).get(match.get_absolute_url()).content.decode()


def test_index_filters_fits_my_skills_and_passes_near_me(east, organiser, farm):
    carpentry = get_or_create_skill("Carpentry")[0]
    tour_need(east, carpentry)
    other_tour = published(
        organiser, "Down south", {"name": "Lyon", "location": Point(4.83, 45.76, srid=4326), "arrive_on": day(3)},
        {"name": "Marseille", "location": Point(5.37, 43.30, srid=4326), "arrive_on": day(5)},
    )
    carl = User.objects.create_user(email="carl@example.com", password="secret", name="Carl",
                                    location=ON_THE_WAY, match_radius=30)
    skill_offer(carl, carpentry)
    client = login(carl)
    for params in ({"fits": "1"}, {"passes": "1"}):
        page = client.get(reverse("tours:api-list"), params).content.decode()
        assert "Clay and seeds" in page and other_tour.title not in page
    # Logged out the filters do nothing
    from django.test import Client

    assert other_tour.title in Client().get(reverse("tours:api-list"), {"fits": "1"}).content.decode()


def test_go_there_together_from_the_event_page(organiser, village, project):
    lena, mia, ole, far = (
        User.objects.create_user(email=f"{name.lower()}@example.com", password="secret", name=name, location=point)
        for name, point in (("Lena", LEIPZIG), ("Mia", LEIPZIG), ("Ole", LEIPZIG), ("Fiona", FAR_AWAY))
    )
    stay(lena, project, day(20), day(25))
    stay(mia, project, day(24), day(30))
    stay(ole, project, day(38), day(40))
    stay(far, project, day(20), day(25))
    page = login(lena).get(project.get_absolute_url()).content.decode()
    assert "Go there together" in page and "1 other from near you is coming in your days" in page
    assert "Go there together" not in login(organiser).get(project.get_absolute_url()).content.decode()

    url = reverse("tours:create") + f"?event={project.pk}"
    assert 'value="Rocket stove"' in login(lena).get(url).content.decode()
    response = login(lena).post(url, {"title": "Together to the stove", "travel_mode": Tour.MODE_TRAIN, "open_to_join": "on", "max_people": 4})
    tour = Tour.objects.get(title="Together to the stove")
    assert response.url == tour.url("plan")
    [stop] = tour.ordered_stops()
    assert stop.event == project and (stop.arrive_on, stop.leave_on) == (day(20), day(25))
    # Someone else can't start one to an event they don't come to
    assert "Rocket stove" not in login(organiser).get(url).content.decode()


# ── Things at the stops ─────────────────────────────────────────────

def thing(holder, type, title, kind=Listing.KIND_TOOL, **fields):
    if holder._meta.model_name == "community":
        fields["community"] = holder
    else:
        fields["owner"] = holder
    return Listing.objects.create(type=type, kind=kind, title=title, **fields)


def test_a_stop_has_what_one_wishes_for(east, farm):
    offer = thing(farm, Listing.TYPE_OFFER, "Two old scythes")
    # Lives in Munich, far from the route, but in the country it goes through
    sami = User.objects.create_user(email="sami@example.com", password="secret", name="Sami",
                                    location=FAR_AWAY, country="DE", match_radius=30)
    wish = thing(sami, Listing.TYPE_WISH, "Scythe")
    matching.suggest_tour(east)
    [suggestion] = tour_suggestions(sami)
    assert suggestion.reason == Suggestion.REASON_HAS and suggestion.own == wish and suggestion.detail == offer
    assert suggestion.text == "The tour Clay and seeds goes to Lindenhof, which offers: Two old scythes"
    assert suggestion.own_text == "your wish: Scythe"
    stops = east.ordered_stops()
    assert f"?from={stops[0].pk}&to={stops[1].pk}&" in suggestion.action_url
    page = login(sami).get(suggestion.action_url).content.decode()
    assert "Lindenhof offers Two old scythes, which I&#x27;m looking for; I&#x27;d like to travel there with you." in page


def test_a_stop_wishes_for_what_one_has_and_the_tour_passes_through_ones_country(east, village):
    wish = thing(village, Listing.TYPE_WISH, "Clay", kind=Listing.KIND_MATERIAL)
    gerd = User.objects.create_user(email="gerd@example.com", password="secret", name="Gerd", country="DE")
    offer = thing(gerd, Listing.TYPE_OFFER, "Clay from our pond", kind=Listing.KIND_MATERIAL)
    abroad = User.objects.create_user(email="ines@example.com", password="secret", name="Ines", country="FR")
    thing(abroad, Listing.TYPE_OFFER, "Clay", kind=Listing.KIND_MATERIAL)
    matching.suggest_tour(east)
    [suggestion] = tour_suggestions(gerd)
    assert suggestion.reason == Suggestion.REASON_WANTS and suggestion.own == offer and suggestion.detail == wish
    assert suggestion.text == "The tour Clay and seeds goes to Elbtal, which is looking for: Clay"
    assert suggestion.own_text == "your offer: Clay from our pond" and suggestion.gives_along
    assert suggestion.action_url == f"{wish.get_absolute_url()}?suggestion={suggestion.pk}"
    page = login(gerd).get(suggestion.action_url).content.decode()
    assert "The tour Clay and seeds comes to you around" in page
    assert "I could give them my Clay from our pond to bring along." in page
    assert "Give it along" in login(gerd).get(reverse("matches:list") + "?type=tours").content.decode()
    assert tour_suggestions(abroad) == []


def test_travelling_and_giving_along_are_one_suggestion_each(east, village):
    thing(village, Listing.TYPE_WISH, "Clay", kind=Listing.KIND_MATERIAL)
    gerd = User.objects.create_user(email="gerd@example.com", password="secret", name="Gerd", country="DE")
    thing(gerd, Listing.TYPE_OFFER, "Clay from our pond", kind=Listing.KIND_MATERIAL)
    stay(gerd, village, day(9), day(16))
    matching.suggest_tour(east)
    matching.suggest_for(gerd)
    assert sorted(s.reason for s in tour_suggestions(gerd)) == [Suggestion.REASON_STAY, Suggestion.REASON_WANTS]


# ── Pausing ─────────────────────────────────────────────────────────

def test_a_pause_silences_travelling_along_but_not_stays_or_giving(east, village):
    permaculture = get_or_create_skill("Permaculture")[0]
    east.learn_skills.add(permaculture)
    thing(village, Listing.TYPE_WISH, "Clay", kind=Listing.KIND_MATERIAL)
    paula = User.objects.create_user(email="paula@example.com", password="secret", name="Paula",
                                     location=ON_THE_WAY, match_radius=30, country="DE")
    skill_wish(paula, permaculture)
    thing(paula, Listing.TYPE_OFFER, "Clay", kind=Listing.KIND_MATERIAL)
    paula.pause_tours("3")
    paula.save()
    matching.suggest_tour(east)
    assert [s.reason for s in tour_suggestions(paula)] == [Suggestion.REASON_WANTS]

    stay(paula, village, day(9), day(16))
    matching.suggest_for(paula)
    assert sorted(s.reason for s in tour_suggestions(paula)) == [Suggestion.REASON_STAY, Suggestion.REASON_WANTS]


def test_what_was_suggested_before_a_pause_is_hidden_during_it(east):
    nina = User.objects.create_user(email="nina@example.com", password="secret", name="Nina",
                                    location=ON_THE_WAY, match_radius=30)
    matching.suggest_tour(east)
    client = login(nina)
    assert "passes near you" in client.get(reverse("matches:list") + "?type=tours").content.decode()
    nina.pause_tours("off")
    nina.save()
    page = client.get(reverse("matches:list") + "?type=tours").content.decode()
    assert "passes near you" not in page and "Off" in page
    assert not send_suggestion_email(nina)


def test_pause_from_the_email_without_logging_in(east):
    from django.test import Client

    from gift_economy.matches.emails import make_suggestions_unsubscribe_token

    nina = User.objects.create_user(email="nina@example.com", password="secret", name="Nina",
                                    location=ON_THE_WAY, match_radius=30)
    matching.suggest_tour(east)
    mail.outbox.clear()
    send_suggestion_email(nina)
    url = reverse("matches:pause_tours", args=[make_suggestions_unsubscribe_token(nina)])
    assert url in mail.outbox[0].body and "Not travelling now? Pause tour suggestions" in mail.outbox[0].body
    page = Client().get(url).content.decode()
    assert "Pause for 1 month" in page and ">On<" not in page
    Client().post(url, {"pause": "6"})
    nina.refresh_from_db()
    assert nina.tours_paused and not nina.tours_off
    assert (nina.tours_paused_until - timezone.localdate()).days in range(181, 185)


def test_add_months_keeps_the_day_or_takes_the_last():
    from datetime import date

    from users.models import add_months

    assert add_months(date(2026, 8, 31), 6) == date(2027, 2, 28)
    assert add_months(date(2026, 11, 13), 1) == date(2026, 12, 13)
    assert add_months(date(2026, 12, 13), 3) == date(2027, 3, 13)


def test_the_profile_shows_the_pause():
    from users.forms import tour_pause_choices

    nina = person("Nina")
    assert tour_pause_choices(nina)[1] == "on"
    assert 'name="tour_suggestions"' in login(nina).get(reverse("users:update")).content.decode()
    nina.pause_tours("1")
    nina.save()
    choices, initial = tour_pause_choices(nina)
    assert initial == "keep" and choices[0][1].startswith("Paused until ")
    nina.pause_tours("keep")
    assert nina.tours_paused and not nina.tours_off
    nina.pause_tours("off")
    assert tour_pause_choices(nina)[1] == "off"


# ── Rides ───────────────────────────────────────────────────────────

LEIPZIG = Point(12.37, 51.34, srid=4326)


@pytest.fixture
def ride(organiser):
    """A ride from Leipzig to Dresden, which ends a few km from the village."""
    return published(
        organiser, "Leipzig → Dresden",
        {"name": "Leipzig", "location": LEIPZIG, "leave_on": day(10)},
        {"name": "Dresden Neustadt", "location": Point(13.75, 51.065, srid=4326), "arrive_on": day(10)},
    )


def test_a_ride_is_suggested_to_who_stays_near_where_it_ends(ride, village):
    village.owner = person("Vera")
    village.save()
    assert ride.is_ride
    lea = User.objects.create_user(email="lea@example.com", password="secret", name="Lea", location=LEIPZIG, match_radius=50)
    match = stay(lea, village, day(10), day(20))
    matching.suggest_tour(ride)
    [suggestion] = tour_suggestions(lea)
    assert suggestion.reason == Suggestion.REASON_STAY and suggestion.own == match and suggestion.is_ride
    assert suggestion.text == f"A ride from Leipzig to Dresden Neustadt on {day(10):%B} {day(10).day}, near Elbtal where you are then"
    assert suggestion.icon == "fa-people-arrows"
    page = login(lea).get(suggestion.action_url).content.decode()
    assert "would like to travel there with you from Leipzig." in page

    mail.outbox.clear()
    send_suggestion_email(lea)
    assert "Tours and rides for you" in mail.outbox[0].body


def test_a_ride_isnt_suggested_for_passing_by_or_to_who_lives_far_from_its_start(ride, village):
    village.owner = person("Vera")
    village.save()
    # Lives right by the way, but stays nowhere near its end
    near = User.objects.create_user(email="nina@example.com", password="secret", name="Nina",
                                    location=Point(13.0, 51.2, srid=4326), match_radius=50)
    far = User.objects.create_user(email="fritz@example.com", password="secret", name="Fritz",
                                   location=FAR_AWAY, match_radius=50)
    stay(far, village, day(10), day(20))
    matching.suggest_tour(ride)
    assert tour_suggestions(near) == [] and tour_suggestions(far) == []


def test_a_ride_towards_home_after_a_stay(organiser, village):
    village.owner = person("Vera")
    village.save()
    ride = published(
        organiser, "Dresden → Leipzig",
        {"name": "Dresden Neustadt", "location": Point(13.75, 51.065, srid=4326), "leave_on": day(12)},
        {"name": "Leipzig", "location": LEIPZIG, "arrive_on": day(12)},
    )
    # Lives in Halle, a bit beyond Leipzig: the ride takes her most of the way
    hanna = User.objects.create_user(email="hanna@example.com", password="secret", name="Hanna",
                                     location=Point(11.97, 51.48, srid=4326), match_radius=30)
    match = stay(hanna, village, day(5), day(12))
    # Lives in Dresden: nothing to go home to with it
    local = User.objects.create_user(email="dora@example.com", password="secret", name="Dora",
                                     location=Point(13.74, 51.05, srid=4326), match_radius=30)
    stay(local, village, day(5), day(12))
    matching.suggest_tour(ride)
    [suggestion] = tour_suggestions(hanna)
    assert suggestion.reason == Suggestion.REASON_HOME and suggestion.own == match
    assert suggestion.text == f"A ride from Dresden Neustadt to Leipzig on {day(12):%B} {day(12).day}, towards your home after Elbtal"
    assert suggestion.own_text == "your stay at Elbtal"
    page = login(hanna).get(suggestion.action_url).content.decode()
    assert "I&#x27;m staying at Elbtal and would like to ride back towards home with you." in page
    assert tour_suggestions(local) == []


def test_people_from_near_each_other_coming_to_the_same_event(project):
    lena, mia, fiona, olga = (
        User.objects.create_user(email=f"{name.lower()}@example.com", password="secret", name=name, location=point)
        for name, point in (("Lena", LEIPZIG), ("Mia", Point(12.40, 51.30, srid=4326)), ("Fiona", FAR_AWAY), ("Oda", LEIPZIG))
    )
    project.community.owner = person("Vera")
    project.community.save()
    mine = stay(lena, project, day(20), day(25))
    theirs = stay(mia, project, day(24), day(30))
    stay(fiona, project, day(20), day(25))
    stay(olga, project, day(20), day(25), status=Match.STATUS_PENDING)
    matching.suggest_together(mine)

    [to_lena] = tour_suggestions(lena)
    [to_mia] = tour_suggestions(mia)
    assert to_lena.reason == Suggestion.REASON_TOGETHER and to_lena.own == mine and to_lena.other == theirs
    assert to_lena.text == "Mia is also coming to Rocket stove around the same days, from near you"
    assert to_lena.url == mia.get_absolute_url() and to_lena.other_user == mia
    assert to_lena.action_url == reverse("tours:create") + f"?stay={mine.pk}"
    assert 'value="Rocket stove"' in login(lena).get(to_lena.action_url).content.decode()
    assert to_mia.other == mine
    assert tour_suggestions(fiona) == [] and tour_suggestions(olga) == []
    page = login(lena).get(reverse("matches:list") + "?type=tours").content.decode()
    assert "Go there together" in page and mia.get_absolute_url() in page

    theirs.status = Match.STATUS_WITHDRAWN
    theirs.save()
    assert tour_suggestions(lena) == [] and tour_suggestions(mia) == []


def test_going_together_to_a_community_only_once_both_are_accepted(village):
    village.owner = person("Vera")
    village.save()
    lena = User.objects.create_user(email="lena@example.com", password="secret", name="Lena", location=LEIPZIG)
    mia = User.objects.create_user(email="mia@example.com", password="secret", name="Mia", location=LEIPZIG)
    ida = User.objects.create_user(email="ida@example.com", password="secret", name="Ida", location=LEIPZIG)
    mine = stay(lena, village, day(20), day(25))
    stay(ida, village, day(20), day(25), status=Match.STATUS_PENDING)
    assert matching.suggest_together(mine) == []
    stay(mia, village, day(22), day(30))
    assert {s.user for s in matching.suggest_together(mine)} == {lena, mia}
    [to_lena] = tour_suggestions(lena)
    assert to_lena.text == "Mia is also coming to Elbtal around the same days, from near you"

    # "Go there together" starts a tour with a stop there, on her days
    response = login(lena).post(to_lena.action_url, {"title": "To Elbtal", "travel_mode": Tour.MODE_TRAIN, "open_to_join": "on", "max_people": 3})
    tour = Tour.objects.get(title="To Elbtal")
    assert response.url == tour.url("plan")
    [stop] = tour.ordered_stops()
    assert stop.community == village and (stop.arrive_on, stop.leave_on) == (day(20), day(25))
