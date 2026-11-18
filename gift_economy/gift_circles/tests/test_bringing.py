"""What people bring to a gift-circle: their own offers and wishes, from its page or from
the offer or wish; suggestions among who comes, however far apart they live; the
reminder the day before."""
from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events import kinds
from events.models import Event
from gift_economy.gift_circles.models import Brought, Guest
from gift_economy.gift_circles.reminders import send_reminders
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match, Suggestion
from users.models import User

pytestmark = pytest.mark.django_db

PARK = Point(9.18, 48.78, srid=4326)
# Far from the park: nearby matching wouldn't pair them
LISBON = Point(-9.14, 38.72, srid=4326)


@pytest.fixture
def host():
    return User.objects.create_user(email="mira@example.com", password="secret", name="Mira", location=PARK)


@pytest.fixture
def person():
    return User.objects.create_user(email="tomek@example.com", password="secret", name="Tomek", location=LISBON)


@pytest.fixture
def stranger():
    return User.objects.create_user(email="ayla@example.com", password="secret", name="Ayla")


def _client(user=None):
    client = Client()
    if user is not None:
        client.force_login(user)
    return client


def _circle(host, days=5, **fields):
    fields.setdefault("title", "Gift-circle in the park")
    return Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=host, is_open=True,
        starts_on=timezone.localdate() + timedelta(days=days), location=PARK,
        location_name="Lindenallee 12, 70173 Stuttgart, Deutschland", **fields,
    )


def _come(event, user):
    _client(user).post(event.url("come"), {"people": "1"})


def _listing(owner, type, title):
    return Listing.objects.create(owner=owner, type=type, kind=Listing.KIND_OTHER, title=title)


def _bring(user, event, listing, **data):
    return _client(user).post(reverse("gift_circles:bring", args=[event.slug]), {"listing": listing.pk, **data})


def test_who_comes_brings_their_own_and_the_page_lists_it(host, person, stranger):
    event = _circle(host)
    _come(event, person)
    wish = _listing(person, Listing.TYPE_WISH, "Help moving a sofa")
    page = _client(person).get(event.get_absolute_url()).content.decode()
    assert "What people bring" in page and "Bring one of yours" in page and "Help moving a sofa" in page

    response = _bring(person, event, wish)
    assert response.url == f"{event.get_absolute_url()}#bring"
    assert Brought.objects.get().listing == wish
    # Everyone sees it; who brings it only who is logged in
    assert "Help moving a sofa" in _client().get(event.get_absolute_url()).content.decode()
    assert "Tomek" not in _client().get(event.get_absolute_url()).content.decode()
    assert "Tomek" in _client(stranger).get(event.get_absolute_url()).content.decode()

    # Taken back, it is gone
    _client(person).post(reverse("gift_circles:take_back", args=[event.slug, wish.pk]))
    assert not Brought.objects.exists()


def test_only_who_comes_or_hosts_brings_and_only_their_own(host, person, stranger):
    event = _circle(host)
    _come(event, person)
    stranger_s = _listing(stranger, Listing.TYPE_OFFER, "Apple tree cuttings")
    page = _client(stranger).get(event.get_absolute_url()).content.decode()
    assert "Bring one of yours" not in page and "Add an offer" not in page
    _bring(stranger, event, stranger_s)
    # Someone else's, even by who comes
    assert _bring(person, event, stranger_s).status_code == 404
    assert not Brought.objects.exists()
    # The host brings too
    offer = _listing(host, Listing.TYPE_OFFER, "A box of jam jars")
    _bring(host, event, offer)
    assert Brought.objects.get().listing == offer


def test_who_stops_coming_no_longer_brings_anything(host, person):
    event = _circle(host)
    _come(event, person)
    _bring(person, event, _listing(person, Listing.TYPE_WISH, "Help moving a sofa"))
    _client(person).post(event.url("not_coming"))
    assert "Help moving a sofa" not in _client(host).get(event.get_absolute_url()).content.decode()


def test_a_new_offer_from_the_gift_circle_s_page_is_brought_to_it(host, person):
    event = _circle(host)
    _come(event, person)
    url = f"{reverse('gifts:create')}?type=offer&gift_circle={event.slug}"
    form_page = _client(person).get(url).content.decode()
    assert f"For {event.title}" in form_page and f'value="{event.slug}"' in form_page
    response = _client(person).post(url, {"type": "offer", "kind": "other", "title": "A bread baking lesson"})
    listing = Listing.objects.get(title="A bread baking lesson")
    assert response.url == f"{event.get_absolute_url()}#bring"
    assert listing.owner == person and Brought.objects.get().listing == listing
    # Not someone's who doesn't come
    stranger = User.objects.create_user(email="ayla@example.com", password="secret")
    response = _client(stranger).post(url, {"type": "offer", "kind": "other", "title": "Two old scythes"})
    assert response.url == Listing.objects.get(title="Two old scythes").get_absolute_url()
    assert Brought.objects.count() == 1


def test_one_s_own_offer_is_brought_to_gift_circles_ahead_one_comes_to(host, person):
    event = _circle(host)
    later = _circle(host, days=20, title="Second gift-circle")
    _come(event, person)
    _come(later, person)
    offer = _listing(person, Listing.TYPE_OFFER, "A bread baking lesson")
    page = _client(person).get(offer.get_absolute_url()).content.decode()
    assert page.count("Bring it to the gift-circle") == 2 and "Second gift-circle" in page
    # Others don't see it
    assert "Bring it to the gift-circle" not in _client(host).get(offer.get_absolute_url()).content.decode()
    response = _bring(person, later, offer, next=offer.get_absolute_url())
    assert response.url == offer.get_absolute_url()
    page = _client(person).get(offer.get_absolute_url()).content.decode()
    assert page.count("Bring it to the gift-circle") == 1 and "Take it back" in page


def test_what_is_brought_is_suggested_among_who_comes_however_far(
    host, person, stranger, django_capture_on_commit_callbacks,
):
    event = _circle(host)
    _come(event, person)
    offer = _listing(host, Listing.TYPE_OFFER, "Scythe")
    _listing(stranger, Listing.TYPE_OFFER, "Old scythe")  # doesn't come
    wish = _listing(person, Listing.TYPE_WISH, "Two old scythes")
    Suggestion.objects.all().delete()  # what the nearby matching found (nothing, they live far apart)
    with django_capture_on_commit_callbacks(execute=True):
        _bring(person, event, wish)
    suggestions = Suggestion.objects.all()
    assert {(s.user, s.own, s.other) for s in suggestions} == {(person, wish, offer), (host, offer, wish)}
    for suggestion in suggestions:
        assert suggestion.reason == Suggestion.REASON_GIFT_CIRCLE and suggestion.gift_circle == event
        assert suggestion.distance_km is None
    page = _client(person).get(reverse("matches:list")).content.decode()
    assert "Comes to the same gift-circle: Gift-circle in the park" in page


def test_who_comes_later_gets_suggestions_for_what_is_brought(host, person, django_capture_on_commit_callbacks):
    event = _circle(host)
    offer = _listing(host, Listing.TYPE_OFFER, "Scythe")
    _bring(host, event, offer)
    wish = _listing(person, Listing.TYPE_WISH, "Two old scythes")
    Suggestion.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        _come(event, person)
    assert Suggestion.objects.filter(user=person, reason=Suggestion.REASON_GIFT_CIRCLE, own_id=str(wish.pk)).exists()


def test_who_comes_hears_the_day_before(host, person, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host, days=1, potluck_note="Soup")
    _come(event, person)
    Guest.objects.create(event=event, name="Jonas", email="jonas@example.com", confirmed_at=timezone.now())
    Guest.objects.create(event=event, name="Theo", email="theo@example.com")  # not confirmed
    _circle(host, days=2, title="Another one")
    offer = _listing(host, Listing.TYPE_OFFER, "Scythe")
    wish = _listing(person, Listing.TYPE_WISH, "Two old scythes")
    with django_capture_on_commit_callbacks(execute=True):
        _bring(host, event, offer)
    mailoutbox.clear()

    assert send_reminders() == 3
    mails = {mail.to[0]: mail for mail in mailoutbox}
    assert set(mails) == {host.email, person.email, "jonas@example.com"}
    assert {mail.subject for mail in mailoutbox} == {"Tomorrow: Gift-circle in the park"}
    host_mail, person_mail, guest_mail = mails[host.email], mails[person.email], mails["jonas@example.com"]
    # The host: their card; nothing to think of, they bring something
    assert reverse("gift_circles:print", args=[event.slug]) in host_mail.body
    assert "Think of a wish and an offer" not in host_mail.body
    # Who comes: what fits theirs, and what to bring
    assert "Mira gives away: Scythe" in person_mail.body and "Two old scythes" in person_mail.body
    assert "Think of a wish and an offer" in person_mail.body and "Soup" in person_mail.body
    assert Suggestion.objects.get(user=person, own_id=str(wish.pk)).emailed_at is not None
    # A guest: their link
    assert reverse("gift_circles:guest", args=[event.slug, Guest.objects.get(name="Jonas").token]) in guest_mail.body
    assert "Lindenallee 12" in guest_mail.body


def test_the_participant_email_says_how_to_bring(host, person, mailoutbox, django_capture_on_commit_callbacks):
    event = _circle(host)
    with django_capture_on_commit_callbacks(execute=True):
        _come(event, person)
    [mail] = [mail for mail in mailoutbox if mail.to == [person.email]]
    assert "Bring it to the gift-circle" in mail.body and f"{event.get_absolute_url()}#bring" in mail.body
    assert Match.objects.get().from_user == person
