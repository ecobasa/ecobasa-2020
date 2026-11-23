"""Coming to a gift-circle: a tour's travellers invited to its own, asking to join one that
isn't open, what people with an account say yes to, and guests without an account."""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events import kinds
from events.models import Event
from gift_economy.gift_circles.models import Attendee, Guest
from gift_economy.matches.models import Match
from notifications.models import Notification
from tours.models import Stop, Tour, Traveller, append_stop
from users.models import User

pytestmark = pytest.mark.django_db

ADDRESS = "Lindenallee 12, 70173 Stuttgart, Deutschland"
PARK = Point(9.18, 48.78, srid=4326)


@pytest.fixture
def host():
    return User.objects.create_user(email="mira@example.com", password="secret", name="Mira")


@pytest.fixture
def person():
    return User.objects.create_user(email="tomek@example.com", password="secret", name="Tomek")


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _circle(host, **fields):
    fields.setdefault("title", "Gift-circle in the park")
    fields.setdefault("is_open", True)
    return Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=host, starts_on=timezone.localdate() + timedelta(days=5),
        location=PARK, location_name=ADDRESS, **fields,
    )


# ── A tour's travellers ─────────────────────────────────────────────

@pytest.fixture
def tour(host):
    tour = Tour.objects.create(title="Seeds along the river", organiser=host)
    day = timezone.localdate() + timedelta(days=10)
    for name, offset in (("Tübingen", 0), ("Market square, Esslingen", 2), ("Plochingen", 4)):
        append_stop(Stop(tour=tour, name=name, location=PARK, arrive_on=day + timedelta(days=offset)))
    return tour


def test_a_tour_s_travellers_at_the_stop_are_invited_to_its_gift_circle(
    tour, host, person, mailoutbox, django_capture_on_commit_callbacks,
):
    first, market, last = tour.ordered_stops()
    Traveller.objects.create(tour=tour, user=person, from_stop=first, to_stop=market)
    gone = User.objects.create_user(email="ayla@example.com", password="secret", name="Ayla")
    Traveller.objects.create(tour=tour, user=gone, to_stop=first)
    with django_capture_on_commit_callbacks(execute=True):
        _client(host).post(reverse("tours:stop_gift_circle", args=[tour.slug, market.pk]), {
            "kind": kinds.GIFT_CIRCLE, "title": "Gift-circle on the market square", "starts_on": market.arrive_on,
            "location_name": market.name, "location": "SRID=4326;POINT (9.18 48.78)",
        })
    event = Event.objects.get()
    [invitation] = [mail for mail in mailoutbox if mail.to == [person.email]]
    assert event.get_absolute_url() in invitation.body and not invitation.attachments
    # The one who invited gets the host's email, whoever left the tour before nothing
    assert {tuple(mail.to) for mail in mailoutbox} == {(host.email,), (person.email,)}
    [notification] = Notification.objects.filter(tag=Notification.TAG_INVITATION)
    assert (notification.recipient, notification.link) == (person, event.get_absolute_url())


def test_a_tour_s_travellers_just_come_to_its_gift_circle_others_ask(tour, host, person):
    Traveller.objects.create(tour=tour, user=person)
    event = Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_tour=tour, title="Gift-circle on the way", is_open=False,
        starts_on=timezone.localdate() + timedelta(days=10), location=PARK, location_name="Market square",
    )
    _client(person).post(event.url("come"), {"people": "1"})
    assert event.matches.get().status == Match.STATUS_ACCEPTED

    stranger = User.objects.create_user(email="ayla@example.com", password="secret", name="Ayla")
    _client(stranger).post(event.url("come"), {"people": "1"})
    assert not event.matches.filter(from_user=stranger).exists()


# ── Asking to join ──────────────────────────────────────────────────

def test_who_can_t_just_come_asks_to_join_without_days_or_needs(host, person, mailoutbox):
    event = _circle(host, is_open=False)
    # The help form isn't for it
    assert _client(person).get(event.url("offer_help")).url == event.url("ask_to_join")
    response = _client(person).post(event.url("ask_to_join"), {
        "people": "2", "message": "I live round the corner.", "keep_on_ecobasa": "on",
    })
    match = event.matches.get()
    assert response.url == match.get_absolute_url()
    assert (match.status, match.people, match.recipient, match.message) == (Match.STATUS_PENDING, 2, host, "I live round the corner.")
    assert Attendee.objects.get(user=person).keep_on_ecobasa
    # Not coming yet, and not twice
    assert event.people_coming() == 0 and not event.shows_place_to(person)
    assert _client(person).get(event.url("ask_to_join")).url == match.get_absolute_url()
    assert Notification.objects.filter(recipient=host).count() == 1
    assert [mail.to for mail in mailoutbox] == [[host.email]]


def test_asking_to_join_is_with_the_events_one_attends(host, person):
    from gift_economy.matches.views import waiting_counts

    event = _circle(host, is_open=False)
    _client(person).post(event.url("ask_to_join"), {"people": "1", "message": "Hello!"})
    match = event.matches.get()
    response = _client(person).get(match.get_absolute_url())
    assert response.context["request_type"] == "events" and not response.context["can_counter"]
    # Not a volunteer visit
    assert match not in _client(host).get(reverse("matches:list") + "?type=volunteer").context["page"].object_list
    assert waiting_counts(host)["events"] == 1 and waiting_counts(host)["volunteer"] == 0


def test_accepted_they_come_and_get_how_it_goes(host, person, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host, is_open=False)
    _client(person).post(event.url("ask_to_join"), {"people": "1", "message": "Hello!"})
    match = event.matches.get()
    mailoutbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        _client(host).post(match.get_absolute_url(), {"action": "accept"})
    match.refresh_from_db()
    assert match.status == Match.STATUS_ACCEPTED
    assert event.people_coming() == 1 and event.shows_place_to(person)
    assert any(mail.attachments for mail in mailoutbox if mail.to == [person.email])


def test_no_yes_when_it_is_full(host, person):
    event = _circle(host, is_open=False, max_people=2)
    _client(person).post(event.url("ask_to_join"), {"people": "2", "message": "Hello!"})
    match = event.matches.get()
    Guest.objects.create(event=event, name="Ayla", email="ayla@example.com", confirmed_at=timezone.now())
    _client(host).post(match.get_absolute_url(), {"action": "accept"})
    match.refresh_from_db()
    assert match.status == Match.STATUS_PENDING


# ── What people with an account say yes to ──────────────────────────

def test_coming_says_whether_offers_and_wishes_stay_on_ecobasa(host, person):
    event = _circle(host)
    _client(person).post(event.url("come"), {"people": "1", "keep_on_ecobasa": "on"})
    assert Attendee.objects.get(event=event, user=person).keep_on_ecobasa
    _client(person).post(reverse("gift_circles:attendee", args=[event.slug]), {})
    assert not Attendee.objects.get(event=event, user=person).keep_on_ecobasa


def test_only_who_comes_changes_it(host, person):
    event = _circle(host)
    _client(person).post(reverse("gift_circles:attendee", args=[event.slug]), {"keep_on_ecobasa": "on"})
    assert not Attendee.objects.exists()


# ── Guests ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def passes_bot_check(monkeypatch):
    import bot_check

    monkeypatch.setattr(bot_check, "check", lambda *args, **kwargs: bot_check.Check())


def test_bots_can_t_sign_up_as_guests(host, mailoutbox, bot_check_fields, monkeypatch):
    import bot_check

    monkeypatch.undo()
    monkeypatch.setattr(bot_check, "MIN_SECONDS", 0)
    event = _circle(host)
    _sign_up(event, **{**bot_check_fields(), "website": "http://spam.example"})
    _sign_up(event, **{**bot_check_fields(), "nonce": "1"})
    assert not Guest.objects.exists() and mailoutbox == []
    _sign_up(event, **bot_check_fields())
    assert Guest.objects.exists()


def _sign_up(event, **fields):
    data = {"name": "Ayla", "email": "ayla@example.com", "people": "1"}
    data.update(fields)
    return Client().post(reverse("gift_circles:guest_sign_up", args=[event.slug]), data)


def _confirm(guest):
    return Client().post(reverse("gift_circles:guest_confirm", args=[guest.event.slug, guest.token]))


def test_visitors_find_coming_as_a_guest_on_an_open_gift_circle(host, person):
    event = _circle(host)
    url = reverse("gift_circles:guest_sign_up", args=[event.slug])
    assert url in Client().get(event.get_absolute_url()).content.decode()
    # Who is logged in says "I'm coming"; who has to ask, asks
    assert url not in _client(person).get(event.get_absolute_url()).content.decode()
    assert _client(person).get(url).url == event.get_absolute_url()
    closed = _circle(host, title="Closed", is_open=False)
    assert Client().get(reverse("gift_circles:guest_sign_up", args=[closed.slug])).url == closed.get_absolute_url()


def test_a_guest_confirms_before_counting_or_hearing_more(host, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host, potluck_note="Soup")
    with django_capture_on_commit_callbacks(execute=True):
        _sign_up(event, people="2", keep_on_ecobasa="on")
    guest = Guest.objects.get()
    assert (guest.people, guest.keep_on_ecobasa, guest.share_email, guest.confirmed_at) == (2, True, False, None)
    [mail] = mailoutbox
    assert reverse("gift_circles:guest_confirm", args=[event.slug, guest.token]) in mail.body
    # Short, and not the exact place yet
    assert ADDRESS not in mail.body and not mail.attachments
    assert event.people_coming() == 0

    # Opening the link doesn't confirm: mail programs open links to check them
    page = Client().get(reverse("gift_circles:guest_confirm", args=[event.slug, guest.token]))
    assert page.status_code == 200 and Guest.objects.get().confirmed_at is None

    with django_capture_on_commit_callbacks(execute=True):
        response = _confirm(guest)
    guest.refresh_from_db()
    assert guest.confirmed_at and response.url == reverse("gift_circles:guest", args=[event.slug, guest.token])
    welcome = mailoutbox[1]
    for text in (welcome.body, welcome.alternatives[0][0]):
        assert ADDRESS in text and reverse("gift_circles:guest", args=[event.slug, guest.token]) in text
    assert welcome.attachments[0][1].startswith("BEGIN:VCALENDAR")
    assert event.people_coming() == 2


def test_signing_up_again_doesn_t_mail_right_away(host, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host)
    with django_capture_on_commit_callbacks(execute=True):
        _sign_up(event)
        _sign_up(event, email="AYLA@example.com", name="Ayla K.")
    assert len(mailoutbox) == 1 and Guest.objects.get().name == "Ayla K."


def test_guests_count_towards_the_limit(host):
    event = _circle(host, max_people=2)
    response = _sign_up(event, people="3")
    assert not Guest.objects.exists() and "people" in response.context["form"].errors
    _sign_up(event, people="2")
    _sign_up(event, email="theo@example.com", name="Theo")
    first, second = Guest.objects.order_by("pk")
    _confirm(first)
    # Full by now
    _confirm(second)
    second.refresh_from_db()
    assert second.confirmed_at is None and not event.takes_people()


def test_a_guest_changes_or_leaves_through_their_link(host):
    event = _circle(host, max_people=3)
    _sign_up(event)
    guest = Guest.objects.get()
    _confirm(guest)
    url = reverse("gift_circles:guest", args=[event.slug, guest.token])
    assert ADDRESS in Client().get(url).content.decode()
    Client().post(url, {"people": "3", "share_email": "on"})
    guest.refresh_from_db()
    assert (guest.people, guest.share_email, guest.keep_on_ecobasa) == (3, True, False)
    assert "people" in Client().post(url, {"people": "4"}).context["form"].errors
    Client().post(url, {"action": "leave"})
    assert not Guest.objects.exists()


def test_a_wrong_link_finds_nothing(host):
    event = _circle(host)
    _sign_up(event)
    other = _circle(host, title="Another one")
    guest = Guest.objects.get()
    assert Client().get(reverse("gift_circles:guest", args=[other.slug, guest.token])).status_code == 404
    assert Client().get(reverse("gift_circles:guest", args=[event.slug, "nothing"])).status_code == 404


def test_a_guest_s_account_brings_their_sign_ups_along(host):
    event = _circle(host)
    _sign_up(event, keep_on_ecobasa="on", people="2")
    guest = Guest.objects.get()
    _confirm(guest)
    client = Client()
    response = client.get(reverse("gift_circles:guest_account", args=[event.slug, guest.token]))
    query = parse_qs(urlparse(response.url).query)
    assert (query["name"], query["email"], query["next"]) == (["Ayla"], ["ayla@example.com"], [event.get_absolute_url()])
    form = client.get(response.url).context["form"]
    assert (form.initial["name"], form.initial["email"]) == ("Ayla", "ayla@example.com")

    user = User.objects.create_user(email="ayla@example.com", password="secret", name="Ayla")
    client.post(reverse("users:login"), {"username": "ayla@example.com", "password": "secret"})
    guest.refresh_from_db()
    assert guest.user == user
    match = event.matches.get(from_user=user)
    assert (match.status, match.is_coming, match.people) == (Match.STATUS_ACCEPTED, True, 2)
    assert Attendee.objects.get(event=event, user=user).keep_on_ecobasa
    # Counted once, as everyone with an account
    assert event.people_coming() == 2


def test_an_account_with_another_email_takes_nothing(host):
    event = _circle(host)
    _sign_up(event)
    guest = Guest.objects.get()
    _confirm(guest)
    other = User.objects.create_user(email="ivo@example.com", password="secret", name="Ivo")
    _client(other).get(reverse("gift_circles:guest_account", args=[event.slug, guest.token]))
    guest.refresh_from_db()
    assert guest.user is None and not event.matches.exists()
