"""Inviting to a gift-circle: members by name and anyone by email, by its host and by who
comes; who was invited comes without asking; an address goes when they don't come."""
from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events import kinds
from events.models import Event
from gift_economy.gift_circles.invitations import EMAIL_LIMIT
from gift_economy.gift_circles.models import Guest, Invitation
from gift_economy.matches.models import Match
from notifications.models import Notification
from users.models import User

pytestmark = pytest.mark.django_db

PARK = Point(9.18, 48.78, srid=4326)


@pytest.fixture
def host():
    return User.objects.create_user(email="mira@example.com", password="secret", name="Mira")


@pytest.fixture
def person():
    return User.objects.create_user(email="tomek@example.com", password="secret", name="Tomek")


@pytest.fixture
def friend():
    return User.objects.create_user(email="ayla@example.com", password="secret", name="Ayla")


def _client(user=None):
    client = Client()
    if user is not None:
        client.force_login(user)
    return client


def _circle(host, **fields):
    fields.setdefault("is_open", False)
    return Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=host, title="Gift-circle in the park",
        starts_on=timezone.localdate() + timedelta(days=5), location=PARK,
        location_name="Lindenallee 12, 70173 Stuttgart, Deutschland", **fields,
    )


def _invite(user, event, **data):
    return _client(user).post(reverse("gift_circles:invite", args=[event.slug]), data)


def _invitation_url(invitation):
    return reverse("gift_circles:invitation", args=[invitation.event.slug, invitation.token])


def test_the_host_invites_a_member_who_then_just_comes(
    host, person, mailoutbox, django_capture_on_commit_callbacks,
):
    event = _circle(host)
    assert not event.may_just_come(person)
    with django_capture_on_commit_callbacks(execute=True):
        _invite(host, event, users=[person.pk], message="Bring your apples!")
    assert event.may_just_come(person)
    assert Notification.objects.filter(recipient=person).count() == 1
    [mail] = mailoutbox
    assert mail.to == [person.email] and "Bring your apples!" in mail.body
    _client(person).post(event.url("come"), {"people": "1"})
    assert event.matches.get(from_user=person).status == Match.STATUS_ACCEPTED


def test_who_comes_invites_too_others_don_t(host, person, friend):
    event = _circle(host, is_open=True)
    assert _invite(person, event, users=[friend.pk]).status_code == 302
    assert not Invitation.objects.exists()
    _client(person).post(event.url("come"), {"people": "1"})
    _invite(person, event, users=[friend.pk])
    assert Invitation.objects.get().user == friend


def test_who_comes_or_was_invited_isn_t_invited_again(host, person, friend, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host, is_open=True)
    _client(person).post(event.url("come"), {"people": "1"})
    with django_capture_on_commit_callbacks(execute=True):
        _invite(host, event, users=[person.pk, friend.pk, host.pk])
        _invite(host, event, users=[friend.pk])
    assert list(event.invitations.values_list("user", flat=True)) == [friend.pk]
    assert [mail.to for mail in mailoutbox] == [[friend.email]]
    found = _client(host).get(reverse("gift_circles:invite_people", args=[event.slug]), {"q": "a"}).json()
    assert found["results"] == []


def test_inviting_by_email_keeps_name_and_address(host, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host)
    with django_capture_on_commit_callbacks(execute=True):
        _invite(host, event, people="Jonas, Jonas@example.org\nlea@example.org\nTheo <theo@example.org>\njonas@example.org")
    assert sorted(event.invitations.values_list("name", "email")) == [
        ("", "lea@example.org"), ("Jonas", "jonas@example.org"), ("Theo", "theo@example.org"),
    ]
    mail = next(mail for mail in mailoutbox if mail.to == ["jonas@example.org"])
    # Roughly where: they don't come yet
    assert "Lindenallee" not in mail.body


def test_a_line_without_an_address_says_which(host):
    event = _circle(host)
    response = _invite(host, event, people="Jonas, jonas@example.org\nLea")
    assert response.status_code == 200 and not Invitation.objects.exists()


def test_addresses_per_gift_circle_are_limited(host):
    event = _circle(host)
    for number in range(EMAIL_LIMIT - 1):
        Invitation.objects.create(event=event, invited_by=host, email=f"guest{number}@example.org")
    _invite(host, event, people="a@example.org\nb@example.org")
    assert event.invitations.count() == EMAIL_LIMIT - 1
    # The ones invited already don't count again
    _invite(host, event, people="guest0@example.org\na@example.org")
    assert event.invitations.count() == EMAIL_LIMIT


def test_invited_by_email_they_come_as_a_guest_without_confirming(
    host, mailoutbox, django_capture_on_commit_callbacks,
):
    event = _circle(host)
    invitation = Invitation.objects.create(event=event, invited_by=host, name="Jonas", email="jonas@example.org")
    with django_capture_on_commit_callbacks(execute=True):
        response = _client().post(_invitation_url(invitation), {
            "action": "guest", "name": "Jonas", "email": "JONAS@example.org", "people": "2",
        })
    guest = Guest.objects.get()
    assert response.url == reverse("gift_circles:guest", args=[event.slug, guest.token])
    assert guest.confirmed_at and event.people_coming() == 2
    assert len(mailoutbox) == 1
    # The guest row keeps the address now
    assert not Invitation.objects.exists()


def test_with_another_address_they_confirm_it(host, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host)
    invitation = Invitation.objects.create(event=event, invited_by=host, email="jonas@example.org")
    with django_capture_on_commit_callbacks(execute=True):
        _client().post(_invitation_url(invitation), {
            "action": "guest", "name": "Jonas", "email": "jonas@example.net", "people": "1",
        })
    assert not Guest.objects.get().confirmed_at
    assert [mail.to for mail in mailoutbox] == [["jonas@example.net"]]


def test_not_coming_deletes_the_address(host):
    event = _circle(host)
    invitation = Invitation.objects.create(event=event, invited_by=host, email="jonas@example.org")
    _client().post(_invitation_url(invitation), {"action": "decline"})
    assert not Invitation.objects.exists()


def test_a_guest_who_leaves_takes_their_address_along(host):
    event = _circle(host)
    invitation = Invitation.objects.create(event=event, invited_by=host, email="jonas@example.org")
    _client().post(_invitation_url(invitation), {
        "action": "guest", "name": "Jonas", "email": "jonas@example.org", "people": "1",
    })
    guest = Guest.objects.get()
    _client().post(reverse("gift_circles:guest", args=[event.slug, guest.token]), {"action": "leave"})
    assert not Guest.objects.exists() and not Invitation.objects.exists()


def test_invited_by_email_they_may_come_with_their_account(host, person):
    event = _circle(host)
    invitation = Invitation.objects.create(event=event, invited_by=host, email="jonas@example.org")
    _client(person).post(_invitation_url(invitation), {"action": "account"})
    invitation.refresh_from_db()
    assert invitation.user == person and invitation.email == ""
    assert event.may_just_come(person)


def test_the_host_sees_everyone_invited_others_their_own(host, person, friend):
    event = _circle(host, is_open=True)
    _client(person).post(event.url("come"), {"people": "1"})
    Invitation.objects.create(event=event, invited_by=host, name="Jonas", email="jonas@example.org")
    Invitation.objects.create(event=event, invited_by=person, user=friend)
    assert "jonas@example.org" not in _client(person).get(reverse("gift_circles:invite", args=[event.slug])).content.decode()
    assert "jonas@example.org" in _client(host).get(reverse("gift_circles:invite", args=[event.slug])).content.decode()
