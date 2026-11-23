import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from gift_economy.matches.emails import make_action_token
from gift_economy.matches.models import Match
from users.models import User

from ..models import Traveller
from .test_tours import FARM_POINT, add, exact, farm, login, organiser, other, published, village  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def station():
    return {"name": "Görlitz station", "location": FARM_POINT.clone()}


@pytest.fixture
def four_stops(organiser, farm, village):
    """A tour of four stops for three people: Olga and two places."""
    from django.contrib.gis.geos import Point

    return published(
        organiser, "Seeds to the coast",
        {"community": farm},
        {"community": village},
        {"name": "Meeting point", "location": Point(10.0, 53.5, srid=4326)},
        {"name": "Harbour", "location": Point(8.8, 53.1, srid=4326)},
        max_people=3,
    )


def person(name):
    return User.objects.create_user(email=f"{name.lower()}@example.com", password="secret", name=name)


def ask(user, tour, start, end, people=1, message="I'd love to come along"):
    response = login(user).post(reverse("tours:join", args=[tour.slug]), {
        "from_stop": start.pk, "to_stop": end.pk, "people": people, "message": message,
    })
    return response, Traveller.objects.filter(user=user, tour=tour).last()


def accept(match, user):
    return login(user).post(match.get_absolute_url(), {"action": "accept"})


def test_the_organiser_travels_with_the_tour(four_stops, organiser):
    traveller = four_stops.travellers.get()
    assert traveller.user == organiser and traveller.is_organiser and traveller.is_counted
    assert four_stops.free_places() == [2, 2, 2]


def test_join_from_stop_2_to_4_and_accept_by_email(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    mail.outbox.clear()
    response, traveller = ask(other, four_stops, stops[1], stops[3])
    match = traveller.match
    assert response.url == match.get_absolute_url()
    assert match.target == four_stops and match.recipient == organiser and match.status == Match.STATUS_PENDING
    assert [m.to for m in mail.outbox] == [[organiser.email]]
    assert "Elbtal → Harbour · 1 person" in mail.outbox[0].body
    # Not on the tour yet
    assert four_stops.free_places() == [2, 2, 2]

    page = login(organiser).get(match.get_absolute_url()).content.decode()
    assert "Elbtal → Harbour" in page

    login(organiser).get(reverse("matches:email_action", args=[make_action_token(match.pk, "accept")]))
    match.refresh_from_db()
    assert match.status == Match.STATUS_ACCEPTED
    assert four_stops.free_places() == [2, 1, 1]
    assert other in [t.user for t in four_stops.present_at(stops[2])]
    assert other not in [t.user for t in four_stops.present_at(stops[0])]


def test_two_requests_for_the_last_place(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    third = person("Tara")
    _r, first = ask(other, four_stops, stops[0], stops[2], people=2)
    _r, second = ask(third, four_stops, stops[1], stops[3])
    assert accept(first.match, organiser).status_code == 302
    first.match.refresh_from_db()
    assert first.match.status == Match.STATUS_ACCEPTED
    assert four_stops.free_places() == [0, 0, 2]

    accept(second.match, organiser)
    second.match.refresh_from_db()
    assert second.match.status == Match.STATUS_PENDING
    # Once the room is taken nobody can ask for it either
    response, _t = ask(person("Uma"), four_stops, stops[1], stops[2])
    assert response.status_code == 200 and "no room" in response.content.decode()


def test_change_the_stretch_while_it_is_open(four_stops, other, organiser):
    stops = four_stops.ordered_stops()
    _r, traveller = ask(other, four_stops, stops[0], stops[1])
    response = login(other).post(reverse("tours:join", args=[four_stops.slug]), {
        "from_stop": stops[1].pk, "to_stop": stops[3].pk, "people": 2,
    })
    traveller.refresh_from_db()
    assert response.status_code == 302
    assert (traveller.from_stop, traveller.to_stop, traveller.people) == (stops[1], stops[3], 2)
    assert Traveller.objects.filter(user=other).count() == 1
    assert "Changed the request" in traveller.match.thread.last().body


def test_a_stretch_must_go_forward(four_stops, other):
    stops = four_stops.ordered_stops()
    response, traveller = ask(other, four_stops, stops[2], stops[1])
    assert response.status_code == 200 and traveller is None


def test_leave_and_remove_need_a_few_words(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    _r, traveller = ask(other, four_stops, stops[0], stops[3])
    accept(traveller.match, organiser)
    assert four_stops.free_places() == [1, 1, 1]

    login(other).post(reverse("tours:leave", args=[four_stops.slug]), {"body": ""})
    assert four_stops.free_places() == [1, 1, 1]
    login(other).post(reverse("tours:leave", args=[four_stops.slug]), {"body": "My back hurts, sorry"})
    traveller.match.refresh_from_db()
    assert traveller.match.status == Match.STATUS_WITHDRAWN
    assert four_stops.free_places() == [2, 2, 2]

    third = person("Tara")
    _r, again = ask(third, four_stops, stops[0], stops[1])
    accept(again.match, organiser)
    remove_url = reverse("tours:remove", args=[four_stops.slug, again.pk])
    assert login(other).post(remove_url, {"body": "bye"}).status_code == 403
    login(organiser).post(remove_url, {"body": "We need the seat for the clay, sorry"})
    again.match.refresh_from_db()
    assert again.match.status == Match.STATUS_DECLINED
    # The organiser can't be taken off, nor leave
    own = four_stops.travellers.get(user=organiser)
    assert login(organiser).post(reverse("tours:remove", args=[four_stops.slug, own.pk]), {"body": "x"}).status_code == 403


def test_an_open_request_can_be_withdrawn(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    _r, traveller = ask(other, four_stops, stops[0], stops[1])
    withdraw_url = reverse("tours:withdraw", args=[four_stops.slug])
    assert withdraw_url in login(other).get(four_stops.get_absolute_url()).content.decode()
    assert withdraw_url in login(other).get(reverse("tours:join", args=[four_stops.slug])).content.decode()
    mail.outbox.clear()
    # No words needed, nobody counts on them yet
    response = login(other).post(withdraw_url, {"body": ""})
    assert response.url == four_stops.get_absolute_url()
    traveller.match.refresh_from_db()
    assert traveller.match.status == Match.STATUS_WITHDRAWN
    assert [m.to for m in mail.outbox] == [[organiser.email]]
    assert "Ask to join" in login(other).get(four_stops.get_absolute_url()).content.decode()

    # Once accepted they leave the tour instead, with a few words
    _r, again = ask(other, four_stops, stops[0], stops[1])
    accept(again.match, organiser)
    login(other).post(withdraw_url)
    again.match.refresh_from_db()
    assert again.match.status == Match.STATUS_ACCEPTED


def test_no_join_on_a_personal_tour(organiser, other, village):
    tour = published(organiser, "Just me", {"community": village}, open_to_join=False, listed=True)
    response = login(other).get(reverse("tours:join", args=[tour.slug]))
    assert response.status_code == 302 and not Traveller.objects.filter(user=other).exists()


def test_an_idea_can_be_joined_as_a_whole(organiser, other):
    tour = published(organiser, "Someday by boat", max_people=4)
    response = login(other).post(reverse("tours:join", args=[tour.slug]), {"people": 2, "message": "Count us in"})
    assert response.status_code == 302
    traveller = Traveller.objects.get(user=other)
    assert traveller.whole_route and traveller.people == 2


def test_pick_up_points_are_rough_until_accepted(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    _r, traveller = ask(other, four_stops, stops[0], stops[1])
    traveller.pickup_name = "Lindenweg 7, 14467 Potsdam, Deutschland"
    traveller.pickup_point = FARM_POINT
    traveller.save()
    name, point = traveller.pickup_place(viewer=organiser)
    assert "Lindenweg" not in name and point.distance(FARM_POINT) > 1e-6
    assert traveller.pickup_place(viewer=other)[1] == FARM_POINT
    accept(traveller.match, organiser)
    traveller.refresh_from_db()
    assert traveller.pickup_place(viewer=organiser)[1] == FARM_POINT


def test_join_requests_list_and_your_tours(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    ask(other, four_stops, stops[0], stops[1])
    received = login(organiser).get(reverse("matches:list"), {"type": "tours"})
    assert received.context["box"] == "received"
    assert [match.from_user for match in received.context["page"]] == [other]
    sent = login(other).get(reverse("matches:list"), {"type": "tours", "box": "sent"})
    assert len(sent.context["page"].object_list) == 1
    # Join requests are not among gift matches
    assert not login(organiser).get(reverse("matches:list"), {"box": "received"}).context["page"].object_list

    mine = login(other).get(reverse("tours:mine")).content.decode()
    assert "Seeds to the coast" in mine and "Asked to join" in mine
    assert "Seeds to the coast" in login(organiser).get(reverse("tours:mine")).content.decode()


def test_only_the_organisers_see_what_a_traveller_could_bring(four_stops, organiser, other):
    stops = four_stops.ordered_stops()
    _, traveller = ask(other, four_stops, stops[0], stops[1])
    url = traveller.match.get_absolute_url()
    assert 'id="person"' in login(organiser).get(url).content.decode()
    assert 'id="person"' not in login(other).get(url).content.decode()
