"""Sharing and handing over the organiser role, inviting someone, and offering a ride."""

from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from gift_economy.matches.models import Match
from notifications.models import Notification

from ..models import Stop, Tour, Traveller
from .test_joining import accept, ask, four_stops, person  # noqa: F401
from .test_tours import farm, login, organiser, other, published, village  # noqa: F401
from .test_visits import ask_host, joined
from .test_visits import tour as visit_tour  # noqa: F401

pytestmark = pytest.mark.django_db


def traveller_of(tour, user):
    return Traveller.objects.get(tour=tour, user=user)


def make_organiser(by, tour, user):
    return login(by).post(reverse("tours:make_organiser", args=[tour.slug, traveller_of(tour, user).pk]))


def invite(by, tour, user, start=None, end=None, people=1, message="Come along, we need a cook"):
    data = {"user": user.pk if user else "", "people": people, "message": message}
    stops = tour.ordered_stops()
    if stops:
        data.update({"from_stop": (start or stops[0]).pk, "to_stop": (end or stops[-1]).pk})
    return login(by).post(reverse("tours:invite", args=[tour.slug]), data)


# ── Sharing the organiser role ──────────────────────────────────────

def test_a_shared_organiser_answers_join_requests(four_stops, organiser, other, django_capture_on_commit_callbacks):
    stops = four_stops.ordered_stops()
    joined(four_stops, other, stops[0], stops[3], 1, django_capture_on_commit_callbacks)
    assert not four_stops.can_edit(other)

    make_organiser(organiser, four_stops, other)
    assert four_stops.can_edit(other)
    assert Notification.objects.filter(recipient=other, verb__contains="made you an organiser").exists()
    assert four_stops.organisers() == [organiser, other]

    # Both organisers hear of a new join request, and either may answer it
    mail.outbox.clear()
    _, traveller = ask(person("Rosa"), four_stops, stops[1], stops[2])
    assert sorted(m.to[0] for m in mail.outbox) == sorted([organiser.email, other.email])
    received = login(other).get(reverse("matches:list") + "?type=tours&box=received").content.decode()
    assert traveller.match.get_absolute_url() in received
    accept(traveller.match, other)
    traveller.match.refresh_from_db()
    assert traveller.match.status == Match.STATUS_ACCEPTED


def test_only_organisers_share_the_role(four_stops, organiser, other, django_capture_on_commit_callbacks):
    stops = four_stops.ordered_stops()
    joined(four_stops, other, stops[0], stops[3], 1, django_capture_on_commit_callbacks)
    rosa = person("Rosa")
    joined(four_stops, rosa, stops[0], stops[1], 1, django_capture_on_commit_callbacks)
    assert make_organiser(rosa, four_stops, other).status_code == 403
    assert not four_stops.is_organiser(other)


# ── Handing over ────────────────────────────────────────────────────

def test_hand_over_moves_open_requests_and_tour_visits(
    visit_tour, organiser, farm, django_capture_on_commit_callbacks,
):
    stops = visit_tour.ordered_stops()
    otto = person("Otto")
    joined(visit_tour, otto, stops[0], stops[2], 1, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        ask_host(organiser, visit_tour, stops[1])
    _, waiting = ask(person("Rosa"), visit_tour, stops[0], stops[1])
    make_organiser(organiser, visit_tour, otto)

    # Only the organiser the matches go to hands over, and only to an organiser on the tour
    assert login(otto).post(reverse("tours:hand_over", args=[visit_tour.slug, traveller_of(visit_tour, organiser).pk])).status_code == 403
    login(organiser).post(reverse("tours:hand_over", args=[visit_tour.slug, traveller_of(visit_tour, otto).pk]))

    visit_tour.refresh_from_db()
    assert visit_tour.organiser == otto
    assert visit_tour.is_organiser(organiser) and visit_tour.is_organiser(otto)
    waiting.match.refresh_from_db()
    assert waiting.match.recipient == otto
    visit = Match.objects.get(pk=Stop.objects.get(pk=stops[1].pk).visit_match_id)
    assert visit.from_user == otto
    # The one before is a companion of the visit now
    assert list(visit.stay_details.companions.all()) == [organiser]
    # Otto's own join request stays as it was
    assert traveller_of(visit_tour, otto).match.recipient == organiser
    assert Notification.objects.filter(recipient=otto, verb__contains="handed the tour").exists()


def test_the_organiser_hands_over_before_leaving(four_stops, organiser, other, django_capture_on_commit_callbacks):
    stops = four_stops.ordered_stops()
    joined(four_stops, other, stops[0], stops[3], 1, django_capture_on_commit_callbacks)
    make_organiser(organiser, four_stops, other)

    login(organiser).post(reverse("tours:leave", args=[four_stops.slug]), {"body": "I broke my leg"})
    assert four_stops.is_organiser(organiser)

    # A shared organiser can leave, and is no organiser any more
    login(other).post(reverse("tours:leave", args=[four_stops.slug]), {"body": "Sorry, work came up"})
    assert not four_stops.is_organiser(other)
    assert traveller_of(four_stops, other).match.status == Match.STATUS_WITHDRAWN

    # The one before can leave once they handed over
    rosa = person("Rosa")
    joined(four_stops, rosa, stops[0], stops[3], 1, django_capture_on_commit_callbacks)
    make_organiser(organiser, four_stops, rosa)
    login(organiser).post(reverse("tours:hand_over", args=[four_stops.slug, traveller_of(four_stops, rosa).pk]))
    login(organiser).post(reverse("tours:leave", args=[four_stops.slug]), {"body": "I broke my leg"})
    four_stops.refresh_from_db()
    assert four_stops.organisers() == [rosa]


# ── Inviting ────────────────────────────────────────────────────────

def test_an_invitation_counts_once_accepted(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    mail.outbox.clear()
    response = invite(organiser, four_stops, other, stops[1], stops[3], people=2)
    assert response.status_code == 302
    traveller = traveller_of(four_stops, other)
    match = traveller.match
    assert traveller.is_invitation and match.from_user == organiser and match.recipient == other
    assert [m.to for m in mail.outbox] == [[other.email]]
    assert "Olga invited you to travel along: Seeds to the coast" in mail.outbox[0].subject
    assert match.kind[0] == "Invitation"
    assert four_stops.free_places() == [2, 2, 2]

    page = login(other).get(four_stops.get_absolute_url()).content.decode()
    assert "invited to travel along." in page and "See the invitation" in page
    # The join page leads to the invitation
    assert login(other).get(reverse("tours:join", args=[four_stops.slug])).url == match.get_absolute_url()

    accept(match, other)
    match.refresh_from_db()
    assert match.status == Match.STATUS_ACCEPTED
    assert four_stops.free_places() == [2, 0, 0]


def test_only_the_one_invited_answers(four_stops, organiser, other, django_capture_on_commit_callbacks):
    stops = four_stops.ordered_stops()
    rosa = person("Rosa")
    joined(four_stops, rosa, stops[0], stops[3], 1, django_capture_on_commit_callbacks)
    make_organiser(organiser, four_stops, rosa)
    invite(organiser, four_stops, other)
    match = traveller_of(four_stops, other).match
    # Another organiser can't accept it for them
    assert login(rosa).post(match.get_absolute_url(), {"action": "accept"}).status_code == 404
    match.refresh_from_db()
    assert match.status == Match.STATUS_PENDING


def test_no_invitation_for_someone_on_the_tour_or_without_room(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    invite(organiser, four_stops, other)
    response = invite(organiser, four_stops, other)
    assert "They are on this tour already, or have been asked." in response.content.decode()
    assert Traveller.objects.filter(tour=four_stops, user=other).count() == 1

    response = invite(organiser, four_stops, person("Rosa"), stops[0], stops[1], people=5)
    assert "There is no room for that many on this stretch" in response.content.decode()
    assert login(other).post(reverse("tours:invite", args=[four_stops.slug]), {}).status_code == 403


def test_people_to_invite_are_found_by_name(four_stops, organiser, other):
    invite(organiser, four_stops, other)
    rosa = person("Rosalind")
    url = reverse("tours:api-people") + f"?tour={four_stops.slug}&q=o"
    assert login(organiser).get(url).json() == {"results": []}
    names = [r["name"] for r in login(organiser).get(url + "s").json()["results"]]
    assert names == ["Rosalind"]
    # Not Otto, who is asked already, nor for someone who doesn't organise the tour
    assert "Otto" not in str(login(organiser).get(url.replace("q=o", "q=Ot")).json())
    assert login(rosa).get(url + "s").status_code == 403


# ── Offering a ride ─────────────────────────────────────────────────

def ride_data(**changes):
    day = timezone.localdate() + timedelta(days=10)
    data = {
        "from-location_name": "Bahnhofsplatz, 04109 Leipzig, Deutschland", "from-location": "SRID=4326;POINT (12.38 51.34)",
        "from-country": "DE",
        "to-location_name": "Kassel, Hessen, Deutschland", "to-location": "SRID=4326;POINT (9.48 51.31)", "to-country": "DE",
        "day": day.isoformat(), "leave_at": "08:30", "travel_mode": Tour.MODE_CAR, "seats": 3,
        "room": "A full boot", "description": "We share fuel.",
    }
    data.update(changes)
    return data


def test_offer_a_ride(organiser):
    response = login(organiser).post(reverse("tours:ride"), ride_data())
    tour = Tour.objects.get()
    assert response.url == tour.get_absolute_url()
    assert tour.title == "Leipzig → Kassel"
    assert tour.is_published and tour.open_to_join and tour.listed and tour.is_ride
    start, end = tour.ordered_stops()
    assert start.leave_at.hour == 8 and start.leave_on == end.arrive_on == tour.starts_on == tour.ends_on
    vehicle = tour.vehicles.get()
    assert vehicle.seats == 3 and vehicle.note == "A full boot" and list(vehicle.drivers.all()) == [organiser]
    assert tour.free_places() == [3]
    assert "Ride" in login(organiser).get(tour.get_absolute_url()).content.decode()


def test_a_ride_on_foot_has_no_vehicle(organiser):
    login(organiser).post(reverse("tours:ride"), ride_data(travel_mode=Tour.MODE_FOOT, seats=2))
    tour = Tour.objects.get()
    assert not tour.vehicles.exists() and tour.max_people == 3 and tour.good_to_know == "A full boot"


def test_a_ride_needs_both_places(organiser):
    response = login(organiser).post(reverse("tours:ride"), ride_data(**{"to-location": ""}))
    assert response.status_code == 200 and not Tour.objects.exists()
    assert "Please choose the place on the map." in response.content.decode()


def test_filters_only_rides_and_free_places(organiser, other, four_stops):
    login(organiser).post(reverse("tours:ride"), ride_data(seats=1))
    ride = Tour.objects.get(vehicles__isnull=False)
    url = reverse("tours:api-list")
    rides = login(other).get(url + "?rides=1").content.decode()
    assert ride.title in rides and four_stops.title not in rides

    _, traveller = ask(other, ride, *ride.ordered_stops())
    accept(traveller.match, organiser)
    free = login(other).get(url + "?free=1").content.decode()
    assert ride.title not in free and four_stops.title in free


def test_the_new_pages_render(four_stops, organiser):
    assert "invite-person-search" in login(organiser).get(reverse("tours:invite", args=[four_stops.slug])).content.decode()
    page = login(organiser).get(reverse("tours:ride")).content.decode()
    assert 'name="from-location_name"' in page and 'name="to-location_name"' in page


def test_invite_from_a_profile(four_stops, organiser, other):
    invite_url = reverse("tours:invite", args=[four_stops.slug]) + f"?user={other.pk}"
    profile = login(organiser).get(other.get_absolute_url()).content.decode()
    assert "Invite to join your tour" in profile and invite_url in profile
    # The invite page starts with them chosen
    assert "invitePerson('Otto')" in login(organiser).get(invite_url).content.decode()
    # Not on one's own profile, not for someone asked already, not for someone who organises nothing
    assert "Invite to join your tour" not in login(organiser).get(organiser.get_absolute_url()).content.decode()
    invite(organiser, four_stops, other)
    assert "Invite to join your tour" not in login(organiser).get(other.get_absolute_url()).content.decode()
    assert "Invite to join your tour" not in login(other).get(organiser.get_absolute_url()).content.decode()


def test_your_tours_cards_offer_what_one_can_do(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    ask(other, four_stops, stops[0], stops[1])
    mine = login(organiser).get(reverse("tours:mine")).content.decode()
    assert "Join requests (1)" in mine and reverse("tours:plan", args=[four_stops.slug]) in mine
    assert reverse("tours:invite", args=[four_stops.slug]) in mine
    theirs = login(other).get(reverse("tours:mine")).content.decode()
    assert "See your request" in theirs and reverse("tours:plan", args=[four_stops.slug]) not in theirs
