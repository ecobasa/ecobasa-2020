"""Tour visits (package 4): a tour asks each host once for the whole group."""

from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from gift_economy.matches.calendar import stays_of
from gift_economy.matches.models import Match
from gift_economy.references.reference_requests import exchange_dates

from ..models import Stop
from .test_joining import accept, ask, person
from .test_tours import farm, login, organiser, other, published, village  # noqa: F401

pytestmark = pytest.mark.django_db

SOON = timezone.localdate() + timedelta(days=30)


@pytest.fixture
def tour(organiser, farm, village):
    """Olga's tour: a meeting point, two weeks at the farm, then the village."""
    village.owner = person("Vince")
    village.save()
    return published(
        organiser, "Clay and seeds",
        {"name": "Meeting point", "location": Point(13.4, 52.5, srid=4326), "arrive_on": SOON, "leave_on": SOON},
        {"community": farm, "arrive_on": SOON + timedelta(days=1), "leave_on": SOON + timedelta(days=14)},
        {"community": village, "arrive_on": SOON + timedelta(days=15), "leave_on": SOON + timedelta(days=17)},
        max_people=6,
    )


def farm_stop(tour):
    return tour.ordered_stops()[1]


def ask_host(user, tour, stop, **data):
    data.setdefault("message", "We'd love to help with the harvest")
    data.setdefault("stay_from", stop.arrive_on.isoformat() if stop.arrive_on else "")
    data.setdefault("stay_to", stop.leave_on.isoformat() if stop.leave_on else "")
    return login(user).post(reverse("tours:ask_host", args=[tour.slug, stop.pk]), data)


def joined(tour, user, start, end, people, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _, traveller = ask(user, tour, start, end, people=people)
        accept(traveller.match, tour.organiser)
    return traveller


def test_a_group_of_four_stays_two_weeks(tour, organiser, farm, django_capture_on_commit_callbacks):
    stops = tour.ordered_stops()
    otto = person("Otto")
    joined(tour, otto, stops[0], stops[2], 3, django_capture_on_commit_callbacks)
    stop = farm_stop(tour)
    assert stop.host_status == Stop.HOST_NOT_ASKED
    assert not farm.shows_place_to(otto)

    mail.outbox.clear()
    response = ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    match = stop.visit_match
    assert response.status_code == 302 and match.recipient == farm.owner
    assert match.people == 4 and list(match.stay_details.companions.all()) == [otto]
    assert stop.host_status == Stop.HOST_ASKED
    assert len(mail.outbox) == 1 and "Clay and seeds" in mail.outbox[0].body
    # The ambassador sees who comes on the match page
    page = login(farm.owner).get(match.get_absolute_url()).content.decode()
    assert "Tour visit" in page and "Otto" in page

    accept(match, farm.owner)
    stop.refresh_from_db()
    assert stop.host_status == Stop.HOST_AGREED
    # The calendar counts four people, every one of the group sees the address
    [stay], _undated = stays_of(farm)
    assert stay.people == 4 and stay.confirmed
    assert farm.shows_place_to(otto) and farm.shows_place_to(organiser)
    assert timezone.localdate(exchange_dates(match)[1]) == stop.leave_on


def test_the_status_is_shown_to_everyone(tour, organiser, farm):
    stop = farm_stop(tour)
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    accept(stop.visit_match, farm.owner)
    page = login(person("Vera")).get(tour.get_absolute_url()).content.decode()
    assert "Agreed" in page and "Not asked yet" in page
    from django.test import Client
    assert "Agreed" in Client().get(tour.get_absolute_url()).content.decode()
    # Only the organisers get the button
    assert reverse("tours:ask_host", args=[tour.slug, stop.pk]) not in page
    own = login(organiser).get(tour.get_absolute_url()).content.decode()
    village_stop = tour.ordered_stops()[2]
    assert reverse("tours:ask_host", args=[tour.slug, village_stop.pk]) in own


def test_only_organisers_ask_and_only_once(tour, organiser, other):
    stop = farm_stop(tour)
    assert ask_host(other, tour, stop).status_code == 403
    ask_host(organiser, tour, stop)
    ask_host(organiser, tour, stop)
    assert Match.objects.filter(stay_details__isnull=False).count() == 1


def test_the_group_changes_and_the_host_is_told(tour, organiser, farm, django_capture_on_commit_callbacks):
    stops = tour.ordered_stops()
    stop = farm_stop(tour)
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    accept(stop.visit_match, farm.owner)
    otto = person("Otto")
    joined(tour, otto, stops[1], stops[2], 2, django_capture_on_commit_callbacks)
    match = Match.objects.get(pk=stop.visit_match_id)
    assert match.people == 3 and otto in match.stay_details.companions.all()
    assert "we are 3 people now" in match.thread.last().body
    # Someone who only rides past isn't in the group
    rider = person("Rita")
    with django_capture_on_commit_callbacks(execute=True):
        _, traveller = ask(rider, tour, stops[0], stops[2])
        traveller.ride_only = True
        traveller.save()
        accept(traveller.match, organiser)
    assert Match.objects.get(pk=match.pk).people == 3


def test_other_days_agreed_move_the_stop(tour, organiser, farm, django_capture_on_commit_callbacks):
    stop = farm_stop(tour)
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    later = stop.arrive_on + timedelta(days=5), stop.leave_on + timedelta(days=5)
    login(farm.owner).post(stop.visit_match.get_absolute_url(), {
        "action": "counter", "body": "Better a bit later",
        "counter_stay_from": later[0].isoformat(), "counter_stay_to": later[1].isoformat(),
    })
    stop.refresh_from_db()
    assert stop.host_status == Stop.HOST_OTHER_DAYS
    login(organiser).post(stop.visit_match.get_absolute_url(), {"action": "accept"})
    stop.refresh_from_db()
    assert (stop.arrive_on, stop.leave_on) == later
    # Now it runs into the village stop
    page = login(organiser).get(tour.get_absolute_url()).content.decode()
    assert "Its days overlap with the stop before" in page


def test_an_open_event_just_hears_the_tour_is_coming(tour, organiser, village):
    event = Event.objects.create(
        community=village, title="Open day", kind=Event.KIND_COMMUNITY_EVENT, is_open=True,
        starts_on=SOON + timedelta(days=15), ends_on=SOON + timedelta(days=15),
    )
    stop = tour.ordered_stops()[2]
    stop.event = event
    stop.save()
    mail.outbox.clear()
    ask_host(organiser, tour, stop, message="")
    stop.refresh_from_db()
    assert stop.host_status == Stop.HOST_COMING and stop.visit_match.is_coming
    assert mail.outbox == []
    # The event and its community list the tour
    vera = login(person("Vera"))
    assert "Tour visits" in vera.get(event.get_absolute_url()).content.decode()
    assert "Clay and seeds" in vera.get(village.get_absolute_url()).content.decode()


def test_a_personal_tour_is_visible_to_the_hosts_it_asked(organiser, farm):
    tour = published(organiser, "Just me", {"community": farm}, open_to_join=False, listed=False)
    assert login(farm.owner).get(tour.get_absolute_url()).status_code == 404
    ask_host(organiser, tour, farm_stop_of(tour))
    assert login(farm.owner).get(tour.get_absolute_url()).status_code == 200


def farm_stop_of(tour):
    return tour.ordered_stops()[0]


def test_withdrawn_visit_can_be_asked_again(tour, organiser):
    stop = farm_stop(tour)
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    match = stop.visit_match
    match.status = Match.STATUS_WITHDRAWN
    match.save()
    stop.refresh_from_db()
    assert stop.can_ask_host
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    assert stop.visit_match_id != match.pk



def test_the_form_has_what_the_volunteer_form_has(tour, organiser, farm):
    """Skills to learn (the tour's, those taught here ticked) and the needs of the
    community's events beside its wishes for things."""
    from gift_economy.gifts import units
    from gift_economy.gifts.models import Listing
    from gift_economy.gifts.skills.models import get_or_create_skill

    clay, sowing = get_or_create_skill("Clay plastering")[0], get_or_create_skill("Seed saving")[0]
    tour.learn_skills.set([clay, sowing])
    Listing.objects.create(community=farm, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill=clay)
    workday = Event.objects.create(
        community=farm, title="Harvest days", kind=Event.KIND_PROJECT, starts_on=SOON, ends_on=SOON + timedelta(days=20),
    )
    hands = Listing.objects.create(
        community=farm, event=workday, type=Listing.TYPE_WISH, kind=Listing.KIND_HANDS,
        quantity=5, unit=units.PEOPLE, description="Helping hands",
    )
    jars = Listing.objects.create(community=farm, type=Listing.TYPE_WISH, kind=Listing.KIND_MATERIAL, title="Jars")
    stop = farm_stop(tour)
    page = login(organiser).get(reverse("tours:ask_host", args=[tour.slug, stop.pk])).content.decode()
    assert "Harvest days" in page and "Jars" in page and "Also wished for" in page
    assert f'value="{clay.pk}"' in page and "checked" in page.split(f'value="{clay.pk}"')[1].split(">")[0]
    assert "checked" not in page.split(f'value="{sowing.pk}"')[1].split(">")[0]

    ask_host(organiser, tour, stop, learn=[str(clay.pk), str(sowing.pk)],
             **{f"need_{hands.pk}": "on", f"quantity_{hands.pk}": "1", f"need_{jars.pk}": "on"})
    stop.refresh_from_db()
    match = stop.visit_match
    assert match.stay_details.practice_skills_list == [clay.get_name(), sowing.get_name()]
    assert {c.listing_id for c in match.contributions.all()} == {hands.pk, jars.pk}
