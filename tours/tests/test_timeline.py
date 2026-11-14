"""What happened on a tour, at its stops: who joined, the hosts that agreed, and the
references written afterwards; a vehicle lent to the tour becomes its vehicle."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.utils import timezone

from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Contribution, Match
from gift_economy.references.models import Reference, ReferenceRequest
from gift_economy.references.reference_requests import send_reference_requests

from ..models import Tour
from ..timeline import timeline_by_stop
from .test_joining import person
from .test_tour_references import after, visited  # noqa: F401
from .test_tours import farm, login, organiser, other, published, village  # noqa: F401
from .test_visits import tour  # noqa: F401

pytestmark = pytest.mark.django_db


def kinds(tour, user):
    stops = tour.ordered_stops()
    return [[entry["kind"] for entry in entries] for entries in timeline_by_stop(tour, stops, user)]


def write(author, subject, match, text, **fields):
    return Reference.objects.create(
        author=author, subject=subject, recipient=subject if hasattr(subject, "email") else subject.get_match_owner(),
        match=match, text=text, **fields,
    )


def test_what_happened_is_told_at_the_stop_where_it_happened(visited, organiser, farm):
    tour = visited.tour
    visit = visited.visit_match
    write(farm.ambassador, tour, visit, "A lovely group, the jars still stand.")
    otto = tour.travellers.get(user__name="Otto").user
    write(otto, farm, visit, "We felt at home.")
    # Rita got off at the farm: what she and the organiser wrote is told there
    rita = tour.travellers.get(user__name="Rita")
    write(organiser, rita.user, rita.match, "Rita carried the heaviest jars.")

    assert kinds(tour, organiser) == [
        ["published", "joined", "joined"],
        ["host_agreed", "reference", "reference", "reference"],
        [],
    ]
    page = login(otto).get(tour.get_absolute_url()).content.decode()
    assert "joined the tour" in page and "agreed to host the group" in page
    assert "We felt at home." in page and "Rita carried the heaviest jars." in page
    # The group's references are at the stops, not listed a second time below, where
    # one adds an experience
    assert page.count("the jars still stand") == 1
    assert "Add experience" in page


def test_visitors_see_the_group_and_what_was_shared(visited, organiser, farm):
    tour = visited.tour
    visit = visited.visit_match
    write(farm.ambassador, tour, visit, "A lovely group, the jars still stand.")
    otto = tour.travellers.get(user__name="Otto").user
    write(otto, farm, visit, "We felt at home.")
    write(organiser, farm, visit, "The best compost we ever turned.", share_publicly=True)

    assert kinds(tour, AnonymousUser()) == [[], ["host_agreed", "reference", "reference"], []]
    page = Client().get(tour.get_absolute_url()).content.decode()
    assert "the jars still stand" in page and "The best compost we ever turned." in page
    assert "We felt at home." not in page and "joined the tour" not in page


def test_a_traveller_is_asked_for_references_once_their_stretch_is_over(visited, organiser):
    rita = visited.tour.travellers.get(user__name="Rita")
    # Accepted a while ago, but the farm (where Rita gets off) is still to come
    send_reference_requests(now=rita.match.responded_at + timedelta(days=8))
    assert not ReferenceRequest.objects.filter(match=rita.match).exists()
    send_reference_requests(now=after(visited))
    assert {r.user for r in ReferenceRequest.objects.filter(match=rita.match)} == {rita.user, organiser}


@pytest.fixture
def boat_lent(tour, organiser, django_capture_on_commit_callbacks):
    """Nils offers his boat for the tour's vehicle need; not answered yet."""
    nils = person("Nils")
    need = Listing.objects.create(tour=tour, type=Listing.TYPE_WISH, kind=Listing.KIND_VEHICLE, title="Sailing boat", lend=True)
    boat = Listing.objects.create(owner=nils, type=Listing.TYPE_OFFER, kind=Listing.KIND_VEHICLE, title="Sailing boat",
                                  lend=True, description="A ketch with a new mainsail")
    with django_capture_on_commit_callbacks(execute=True):
        match = Match(from_user=nils, recipient=organiser, message="Take her across")
        match.target = need
        match.save()
        Contribution.objects.bulk_create([Contribution(match=match, listing=need), Contribution(match=match, listing=boat)])
    return match, boat


def answer(match, status, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        match.status = status
        match.responded_at = timezone.now()
        match.save()


def test_a_vehicle_lent_to_the_tour_becomes_its_vehicle(tour, organiser, boat_lent, django_capture_on_commit_callbacks):
    match, boat = boat_lent
    assert not tour.vehicles.exists()
    answer(match, Match.STATUS_ACCEPTED, django_capture_on_commit_callbacks)
    vehicle = tour.vehicles.get()
    assert (vehicle.listing, vehicle.label, vehicle.note) == (boat, "Sailing boat", "A ketch with a new mainsail")
    # It fills the tour, the organiser at the wheel
    assert list(vehicle.drivers.all()) == [organiser] and vehicle.places == tour.max_people
    # Saved again, it stays one vehicle
    answer(match, Match.STATUS_ACCEPTED, django_capture_on_commit_callbacks)
    assert tour.vehicles.count() == 1
    # Called off, it goes again
    answer(match, Match.STATUS_WITHDRAWN, django_capture_on_commit_callbacks)
    assert not Tour.objects.get(pk=tour.pk).vehicles.exists()


def test_a_reference_after_a_gift_taken_along_names_no_stay(visited, organiser):
    tour = visited.tour
    gift = Listing.objects.create(owner=person("Ana"), type=Listing.TYPE_WISH, kind=Listing.KIND_FOOD, title="Honey")
    match = Match(from_user=organiser, recipient=gift.owner)
    match.target = gift
    match.save()
    reference = write(gift.owner, tour, match, "Sweet.")
    assert reference.visited is None
    assert Reference.objects.get(pk=reference.pk).content_type == ContentType.objects.get_for_model(Tour)
