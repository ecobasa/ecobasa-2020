"""The video call of an online gift-circle: its page on ecobasa for who comes, the room in
it from an hour before, and the emails that link to the page, never to the room."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events import kinds
from events.models import Event
from gift_economy.gift_circles import video
from gift_economy.gift_circles.models import Guest
from gift_economy.matches.models import Match, StayDetails
from users.models import User

pytestmark = pytest.mark.django_db

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture(autouse=True)
def server(settings):
    settings.JITSI_BASE_URL = "https://meet.example.org"
    settings.JITSI_EMBED = True


@pytest.fixture
def host():
    return User.objects.create_user(email="mira@example.com", password="secret", name="Mira")


@pytest.fixture
def person():
    return User.objects.create_user(email="tomek@example.com", password="secret", name="Tomek")


def _client(user=None):
    client = Client()
    if user:
        client.force_login(user)
    return client


def _circle(host, starts=None, **fields):
    """An online gift-circle starting at `starts` (Berlin time), in five days by default."""
    starts = starts or datetime.combine(timezone.localdate() + timedelta(days=5), time(19, 0), tzinfo=BERLIN)
    starts = starts.astimezone(BERLIN)
    return Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=host, title="Gift-circle online", is_open=True, is_online=True,
        starts_on=starts.date(), ends_on=starts.date(), starts_at=starts.time().replace(second=0, microsecond=0),
        ends_at=time(21, 0), **fields,
    )


def _come(event, user):
    match = Match(from_user=user, recipient=event.manager, message="", status=Match.STATUS_ACCEPTED)
    match.target = event
    match.save()
    StayDetails.objects.create(match=match, volunteer_mode=StayDetails.MODE_COME, people=1)


def test_its_room_is_on_the_server_set_and_nobody_guesses_it(host, settings):
    event, other = _circle(host), _circle(host)
    url = video.room_url(event)
    assert url.startswith("https://meet.example.org/ecobasa-") and url != video.room_url(other)
    settings.JITSI_BASE_URL = "https://meet.ffmuc.net/"
    assert video.room_url(event).startswith("https://meet.ffmuc.net/ecobasa-")


def test_the_page_shows_the_room_to_who_comes_from_an_hour_before(host, person):
    event = _circle(host, starts=timezone.now() + timedelta(minutes=50))
    url = reverse("gift_circles:video_call", args=[event.slug])
    assert _client().get(url)["Location"].startswith(reverse("users:login"))
    assert _client(person).get(url)["Location"] == event.get_absolute_url()
    _come(event, person)
    response = _client(person).get(url)
    assert response.context["embed_url"].startswith(video.room_url(event) + "#config.disableDeepLinking=true")
    assert 'userInfo.displayName=%22Tomek%22' in response.context["embed_url"]
    assert _client(host).get(url).context["embed_url"]


def test_before_the_hour_the_room_stays_hidden(host, person):
    event = _circle(host, starts=timezone.now() + timedelta(hours=3))
    _come(event, person)
    response = _client(person).get(reverse("gift_circles:video_call", args=[event.slug]))
    assert not response.context["room_url"] and video.room_url(event).encode() not in response.content


def test_a_server_that_does_not_allow_embedding_gets_a_link(host, person, settings):
    settings.JITSI_EMBED = False
    event = _circle(host, starts=timezone.now() + timedelta(minutes=30))
    _come(event, person)
    response = _client(person).get(reverse("gift_circles:video_call", args=[event.slug]))
    assert not response.context["embed_url"] and response.context["room_url"] == video.room_url(event)
    # The host's own link on another server is never embedded
    settings.JITSI_EMBED = True
    event.video_url = "https://talk.example.net/our-circle"
    event.save()
    response = _client(person).get(reverse("gift_circles:video_call", args=[event.slug]))
    assert not response.context["embed_url"] and response.context["room_url"] == event.video_url


def test_a_guest_joins_through_their_link(host):
    event = _circle(host, starts=timezone.now() + timedelta(minutes=30))
    guest = Guest.objects.create(event=event, name="Jonas", email="jonas@example.com")
    url = reverse("gift_circles:guest_video_call", args=[event.slug, guest.token])
    assert "confirm" in _client().get(url)["Location"]
    guest.confirmed_at = timezone.now()
    guest.save()
    assert "Jonas" in _client().get(url).context["embed_url"]


def test_an_hour_before_who_comes_gets_the_page_once(host, person, mailoutbox):
    event = _circle(host, starts=timezone.now() + timedelta(minutes=58))
    later = _circle(host, starts=timezone.now() + timedelta(hours=2))
    _come(event, person)
    Guest.objects.create(event=event, name="Jonas", email="jonas@example.com", confirmed_at=timezone.now())
    assert video.send_links() == 3
    assert video.send_links() == 0
    mails = {mail.to[0]: mail for mail in mailoutbox}
    assert set(mails) == {host.email, person.email, "jonas@example.com"}
    assert reverse("gift_circles:video_call", args=[event.slug]) in mails[person.email].body
    guest = Guest.objects.get()
    assert reverse("gift_circles:guest_video_call", args=[event.slug, guest.token]) in mails["jonas@example.com"].body
    # Never the room itself
    assert not any(video.room_url(event) in mail.body for mail in mailoutbox)
    later.refresh_from_db()
    assert later.video_call_mailed_at is None


def test_the_confirmation_links_to_the_video_call_and_the_calendar_file_has_it(
    host, person, mailoutbox, django_capture_on_commit_callbacks,
):
    event = _circle(host)
    with django_capture_on_commit_callbacks(execute=True):
        _client(person).post(reverse("events:gift_circle_come", args=[event.slug]), {"people": 1})
    [mail] = [mail for mail in mailoutbox if mail.to == [person.email]]
    page = reverse("gift_circles:video_call", args=[event.slug])
    assert page in mail.body
    calendar = mail.attachments[0][1]
    assert "LOCATION:http" in calendar and page in calendar.replace("\r\n ", "")


def test_its_times_are_in_its_timezone_and_say_so(host, person, mailoutbox, django_capture_on_commit_callbacks):
    # 19:00 in Mexico City is 01:00 UTC the next day: it opens at 18:00 there, still closed in Berlin's evening
    mexico = ZoneInfo("America/Mexico_City")
    day = timezone.localdate() + timedelta(days=5)
    event = _circle(host, starts=datetime.combine(day, time(19, 0), tzinfo=BERLIN), timezone="America/Mexico_City")
    assert not video.is_open(event, datetime.combine(day, time(18, 30), tzinfo=BERLIN))
    assert video.is_open(event, datetime.combine(day, time(18, 30), tzinfo=mexico))
    with django_capture_on_commit_callbacks(execute=True):
        _client(person).post(reverse("events:gift_circle_come", args=[event.slug]), {"people": 1})
    [mail] = [mail for mail in mailoutbox if mail.to == [person.email]]
    utc = (day + timedelta(days=1)).strftime("%Y%m%d")
    assert f"DTSTART:{utc}T010000Z" in mail.attachments[0][1]
