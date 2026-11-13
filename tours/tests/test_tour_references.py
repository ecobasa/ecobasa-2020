"""References about a tour: the whole group at a visit, with who was there."""

from datetime import datetime, time, timedelta

import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gift_economy.references.models import Reference, ReferenceRequest
from gift_economy.references.reference_requests import send_reference_requests

from ..models import Tour
from .test_joining import accept, person
from .test_tours import farm, login, organiser, other, published, village  # noqa: F401
from .test_visits import ask_host, farm_stop, joined, tour  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def visited(tour, organiser, farm, django_capture_on_commit_callbacks):
    """Olga, Otto and Rita stayed at the farm; Rita got off there."""
    stops = tour.ordered_stops()
    joined(tour, person("Otto"), stops[0], stops[2], 1, django_capture_on_commit_callbacks)
    joined(tour, person("Rita"), stops[0], stops[1], 1, django_capture_on_commit_callbacks)
    stop = farm_stop(tour)
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    accept(stop.visit_match, farm.owner)
    stop.refresh_from_db()
    return stop


def after(stop):
    end = timezone.make_aware(datetime.combine(stop.leave_on, time.min))
    return end + timedelta(days=settings.REFERENCE_REQUEST_DELAY_DAYS, hours=1)


def test_after_the_visit_host_and_group_are_asked(visited, organiser, farm):
    match = visited.visit_match
    assert sorted(u.name for u in match.stay_details.companions.all()) == ["Otto", "Rita"]
    send_reference_requests(now=after(visited))
    asked = {r.user.name for r in ReferenceRequest.objects.filter(match=match)}
    assert asked == {"Olga", "Otto", "Rita", farm.owner.name}


def test_the_host_writes_about_the_group_and_about_one_of_them(visited, farm):
    match = visited.visit_match
    send_reference_requests(now=after(visited))
    key = ReferenceRequest.objects.get(match=match, user=farm.owner).key
    url = reverse("references:request", args=[key])
    page = Client().get(url).content.decode()
    assert "The whole group" in page and "Otto" in page and "Who was there" in page

    otto = match.stay_details.companions.get(name="Otto")
    rita = match.stay_details.companions.get(name="Rita")
    Client().post(url, {"impression": "positive", "text": "A lovely group, the jars still stand.", "people": [str(otto.pk)]})
    group_reference = Reference.objects.get(content_type=ContentType.objects.get_for_model(Tour))
    assert group_reference.subject == visited.tour and list(group_reference.people.all()) == [otto]

    Client().post(f"{url}?about={rita.pk}", {"impression": "positive", "text": "Rita fixed our pump."})
    assert Reference.objects.get(author=farm.owner, object_id=str(rita.pk)).subject == rita

    # The tour page lists the group's reference with who was there; Rita's stays on her profile
    page = Client().get(visited.tour.get_absolute_url()).content.decode()
    assert "the jars still stand" in page and "Rita fixed our pump" not in page
    # It names where the group stayed
    assert group_reference.visited == visited.community and visited.community.get_absolute_url() in page


def test_the_group_writes_about_the_host(visited, farm):
    match = visited.visit_match
    send_reference_requests(now=after(visited))
    otto = match.stay_details.companions.get(name="Otto")
    key = ReferenceRequest.objects.get(match=match, user=otto).key
    Client().post(reverse("references:request", args=[key]), {"impression": "positive", "text": "We felt at home."})
    assert Reference.objects.get(author=otto).subject == farm


def test_the_guestbook_takes_entries_at_any_stop_and_waits_for_strangers(visited, organiser, farm):
    tour = visited.tour
    stops = tour.ordered_stops()
    url = reverse("references:save", args=[ContentType.objects.get_for_model(Tour).pk, tour.pk])
    # A traveller tells the journey, as often as they like, without an impression to give
    otto = tour.travellers.get(user__name="Otto").user
    page = login(otto).get(tour.get_absolute_url()).content.decode()
    assert "Add experience" in page and "Where was it?" in page and 'name="impression"' not in page
    login(otto).post(url, {"text": "We met at the meeting point.", "place": str(stops[0].pk)})
    login(otto).post(url, {"text": "Mud to our knees.", "place": str(stops[1].pk), "people": [str(otto.pk)]})
    entries = Reference.objects.filter(author=otto).order_by("pk")
    assert [(r.place, r.pending) for r in entries] == [(stops[0], False), (stops[1], False)]
    # The host is known to the tour too
    login(farm.owner).post(url, {"impression": "positive", "text": "Come back!", "place": str(stops[1].pk)})
    assert not Reference.objects.get(author=farm.owner).pending
    # Someone it doesn't know waits, seen only by them and the travellers
    vera = person("Vera")
    login(vera).post(url, {"impression": "positive", "text": "They helped at our market.", "place": str(stops[2].pk)})
    entry = Reference.objects.get(author=vera)
    assert entry.pending and entry.recipient == organiser
    assert "They helped at our market." in login(vera).get(tour.get_absolute_url()).content.decode()
    assert "They helped at our market." not in login(person("Walt")).get(tour.get_absolute_url()).content.decode()
    page = login(otto).get(tour.get_absolute_url()).content.decode()
    assert "Waiting for confirmation" in page
    # Strangers can't confirm it, a traveller can
    confirm = reverse("references:confirm", args=[entry.pk, "confirm"])
    assert login(vera).post(confirm).status_code == 404
    login(otto).post(confirm)
    assert "They helped at our market." in Client().get(tour.get_absolute_url()).content.decode()
    # Editing changes that entry, not a new one
    login(vera).post(url, {"impression": "positive", "text": "They helped a lot.", "place": str(stops[2].pk), "reference": str(entry.pk)})
    assert Reference.objects.filter(author=vera).count() == 1 and Reference.objects.get(author=vera).text == "They helped a lot."

def test_a_host_who_travels_along_is_asked_once_as_host(tour, organiser, farm, django_capture_on_commit_callbacks):
    stops = tour.ordered_stops()
    joined(tour, farm.owner, stops[0], stops[2], 1, django_capture_on_commit_callbacks)
    stop = farm_stop(tour)
    ask_host(organiser, tour, stop)
    stop.refresh_from_db()
    accept(stop.visit_match, farm.owner)
    send_reference_requests(now=after(stop))
    request = ReferenceRequest.objects.get(match=stop.visit_match, user=farm.owner)
    page = Client().get(reverse("references:request", args=[request.key])).content.decode()
    assert "The whole group" in page


def test_once_over_the_tour_page_says_how_it_went_and_whom_to_write_about(visited, organiser, farm):
    tour = visited.tour
    assert "How the tour went" not in Client().get(tour.get_absolute_url()).content.decode()
    # Move the tour into the past
    for stop in tour.stops.all():
        stop.arrive_on -= timedelta(days=120)
        stop.leave_on -= timedelta(days=120)
        stop.save(update_fields=["arrive_on", "leave_on"])
    tour.rebuild_route()
    assert tour.is_over

    otto = tour.travellers.get(user__name="Otto").user
    page = login(otto).get(tour.get_absolute_url()).content.decode()
    assert "How the tour went" in page and "Where it went" in page and "Write references" in page
    assert f"{farm.get_absolute_url()}#references" in page
    assert f"{organiser.get_absolute_url()}#references" in page
    assert f"{otto.get_absolute_url()}#references" not in page
    # The host writes about the group
    page = login(farm.owner).get(tour.get_absolute_url()).content.decode()
    assert f"{tour.get_absolute_url()}#references" in page
    # Someone who wasn't there only reads how it went
    page = login(person("Vera")).get(tour.get_absolute_url()).content.decode()
    assert "How the tour went" in page and "Write references" not in page
