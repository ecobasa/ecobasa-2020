"""What gift-circles add to events: the emails with the instructions and the calendar
file, the printable card and Giftsheet, the host's guide and the potluck."""
from datetime import date, time, timedelta

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from communities.models import Community
from events import kinds
from events.ics import ics
from events.models import Event
from gift_economy.gift_circles.timings import timings
from users.models import User

pytestmark = pytest.mark.django_db

ADDRESS = "Lindenallee 12, 70173 Stuttgart, Deutschland"


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


def _invite(host, **fields):
    day = timezone.localdate() + timedelta(days=5)
    data = {
        "kind": kinds.GIFT_CIRCLE, "title": "Gift-circle in the park", "starts_on": day, "starts_at": "19:00",
        "ends_at": "20:30", "location_name": ADDRESS, "location": "SRID=4326;POINT (9.18 48.78)", "is_open": "on",
        "potluck_note": "Soup and bread",
    }
    data.update(fields)
    return _client(host).post(reverse("events:gift_circle_create"), data)


def _circle(host, **fields):
    fields.setdefault("title", "Gift-circle in the park")
    return Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=host, starts_on=timezone.localdate() + timedelta(days=5), is_open=True,
        location=Point(9.18, 48.78, srid=4326), location_name=ADDRESS, **fields,
    )


# ── Emails ──────────────────────────────────────────────────────────

def test_whoever_invites_gets_the_facilitator_card_and_the_calendar_file(host, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _invite(host)
    event = Event.objects.get()
    [mail] = mailoutbox
    assert mail.to == [host.email]
    for text in (mail.body, mail.alternatives[0][0]):
        assert ADDRESS in text
        assert reverse("gift_circles:print", args=[event.slug]) in text
    [(name, calendar, mimetype)] = mail.attachments
    assert name == "gift-circle-in-the-park.ics" and mimetype == "text/calendar"
    assert "DTSTART:" + event.starts_on.strftime("%Y%m%d") + "T190000" in calendar


def test_editing_sends_nothing(host, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host)
    with django_capture_on_commit_callbacks(execute=True):
        _client(host).post(event.url("edit"), {
            "kind": kinds.GIFT_CIRCLE, "title": "Renamed", "starts_on": event.starts_on,
            "location_name": ADDRESS, "location": "SRID=4326;POINT (9.18 48.78)",
        })
    assert Event.objects.get().title == "Renamed" and mailoutbox == []


def test_who_comes_gets_how_it_goes_with_the_exact_place(host, person, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host, potluck_note="Soup and bread")
    with django_capture_on_commit_callbacks(execute=True):
        _client(person).post(event.url("come"), {"people": "1"})
    [mail] = mailoutbox
    assert mail.to == [person.email]
    for text in (mail.body, mail.alternatives[0][0]):
        assert ADDRESS in text
    assert mail.attachments[0][1].startswith("BEGIN:VCALENDAR")


def test_coming_to_another_kind_sends_nothing(person, mailoutbox, django_capture_on_commit_callbacks):
    ambassador = User.objects.create_user(email="ivo@example.com", password="secret", name="Ivo")
    community = Community.objects.create(name="Wiesengrund", ambassador=ambassador)
    event = Event.objects.create(
        kind=kinds.COMMUNITY_EVENT, community=community, title="Open day", is_open=True,
        starts_on=timezone.localdate() + timedelta(days=3),
    )
    with django_capture_on_commit_callbacks(execute=True):
        _client(person).post(event.url("come"), {"people": "1"})
    assert event.matches.filter(from_user=person).exists() and mailoutbox == []


# ── The form ────────────────────────────────────────────────────────

def test_only_gift_circles_keep_a_potluck_note(host):
    _invite(host, kind=kinds.GIFT_CIRCLE)
    assert Event.objects.get().potluck_note == "Soup and bread"
    ambassador = User.objects.create_user(email="ivo@example.com", password="secret", name="Ivo")
    community = Community.objects.create(name="Wiesengrund", ambassador=ambassador)
    day = timezone.localdate() + timedelta(days=5)
    _client(ambassador).post(f"{reverse('events:create', args=[community.slug])}?kind={kinds.PROJECT}", {
        "kind": kinds.PROJECT, "title": "Straw-bale wall", "starts_on": day, "ends_on": day,
        "potluck_note": "Soup", "needs-TOTAL_FORMS": "0", "needs-INITIAL_FORMS": "0",
    })
    assert Event.objects.get(kind=kinds.PROJECT).potluck_note == ""


def test_hours_go_in_steps_of_15_minutes(host):
    response = _invite(host, starts_at="19:10")
    assert not Event.objects.exists()
    assert "starts_at" in response.context["form"].errors


# ── Printing ────────────────────────────────────────────────────────

def test_the_card_and_the_giftsheet_print_for_anyone(host):
    event = _circle(host)
    response = Client().get(reverse("gift_circles:print", args=[event.slug]))
    page = response.content.decode()
    assert response.status_code == 200
    # Its place shows on its page, to who may know it
    assert ADDRESS not in page


def test_only_gift_circles_have_a_giftsheet(host):
    community = Community.objects.create(name="Wiesengrund", ambassador=host)
    event = Event.objects.create(kind=kinds.PROJECT, community=community, title="Straw-bale wall")
    assert Client().get(reverse("gift_circles:print", args=[event.slug])).status_code == 404


# ── The calendar file ───────────────────────────────────────────────

def test_a_calendar_file_without_hours_takes_whole_days(host):
    event = _circle(host)
    event.starts_on = event.ends_on = date(2026, 12, 3)
    lines = ics(event).split("\r\n")
    assert "DTSTART;VALUE=DATE:20261203" in lines and "DTEND;VALUE=DATE:20261204" in lines


def test_a_calendar_file_escapes_and_folds(host):
    event = _circle(host, title="Gifts, wishes; and " + "ä" * 60, starts_at=time(19), ends_at=time(20, 30))
    calendar = ics(event, "Lindenallee 12, Stuttgart")
    assert "LOCATION:Lindenallee 12\\, Stuttgart" in calendar
    assert all(len(line.encode()) <= 75 for line in calendar.split("\r\n"))
    unfolded = calendar.replace("\r\n ", "")
    assert "SUMMARY:Gifts\\, wishes\\; and " + "ä" * 60 in unfolded
    assert "DTEND:" + event.starts_on.strftime("%Y%m%d") + "T203000" in unfolded


# ── The rounds' minutes ─────────────────────────────────────────────

def test_the_rounds_take_1_5_hours_without_hours(host):
    shares = timings(_circle(host))
    assert (shares["welcome"], shares["wishes"], shares["offers"], shares["thanks"], shares["close"]) == (10, 35, 30, 10, 5)
    assert shares["duration"] == ""


def test_the_rounds_share_out_the_time_the_host_gave(host):
    long = timings(_circle(host, starts_at=time(18), ends_at=time(21)))
    assert (long["wishes"], long["offers"], long["duration"]) == (70, 60, "3 hours")
    short = timings(_circle(host, title="Short", starts_at=time(18), ends_at=time(18, 45)))
    assert (short["welcome"], short["wishes"], short["close"], short["duration"]) == (5, 20, 5, "45 minutes")
