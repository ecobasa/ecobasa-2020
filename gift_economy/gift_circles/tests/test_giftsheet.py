"""The Giftsheet: who sees and writes it, the person picker and walk-ins, what people
bring on it, answering a line, scribes, photos, refreshing, and closing it into offers,
wishes and matches."""
from datetime import timedelta
from io import BytesIO

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events import kinds
from events.models import Event
from gift_economy.gift_circles import giftsheet as sheets
from gift_economy.gift_circles.invitations import EMAIL_LIMIT, emails_left
from gift_economy.gift_circles.models import Attendee, Entry, GiftsheetPhoto, Guest, Idea, Invitation, Scribe
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match
from users.models import User

pytestmark = pytest.mark.django_db

PARK = Point(9.18, 48.78, srid=4326)


@pytest.fixture
def host():
    return User.objects.create_user(email="mira@example.com", password="secret", name="Mira", location=PARK)


@pytest.fixture
def person():
    return User.objects.create_user(email="tomek@example.com", password="secret", name="Tomek", location=PARK)


@pytest.fixture
def other():
    return User.objects.create_user(email="ayla@example.com", password="secret", name="Ayla", location=PARK)


@pytest.fixture
def stranger():
    return User.objects.create_user(email="jonas@example.com", password="secret", name="Jonas")


def _client(user=None):
    client = Client()
    if user is not None:
        client.force_login(user)
    return client


def _circle(host, days=0, **fields):
    fields.setdefault("title", "Gift-circle in the park")
    return Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=host, is_open=True,
        starts_on=timezone.localdate() + timedelta(days=days), location=PARK,
        location_name="Lindenallee 12, 70173 Stuttgart, Deutschland", **fields,
    )


def _come(event, user, keep=False):
    data = {"people": "1"}
    if keep:
        data["keep_on_ecobasa"] = "on"
    _client(user).post(event.url("come"), data)


def _guest(event, name="Lena", email="lena@example.com"):
    return Guest.objects.create(event=event, name=name, email=email, confirmed_at=timezone.now())


def _url(event):
    return reverse("gift_circles:giftsheet", args=[event.slug])


def _entry_url(event, entry):
    return reverse("gift_circles:giftsheet_entry", args=[event.slug, entry.pk])


def _add(user, event, text, type="wish", **data):
    return _client(user).post(_url(event), {"type": type, "text": text, **data})


def test_who_came_the_host_and_scribes_see_it_others_dont(host, person, stranger):
    event = _circle(host)
    _come(event, person)
    assert _client(host).get(_url(event)).status_code == 200
    assert _client(person).get(_url(event)).status_code == 200
    assert _client(stranger).get(_url(event)).url == event.get_absolute_url()
    assert "login" in Client().get(_url(event)).url
    page = _client(person).get(event.get_absolute_url()).content.decode()
    assert "Open the Giftsheet" in page
    assert "Open the Giftsheet" not in _client(stranger).get(event.get_absolute_url()).content.decode()


def test_it_starts_with_what_people_bring_and_follows_bringing(host, person):
    event = _circle(host, days=3)
    _come(event, person)
    wish = Listing.objects.create(owner=person, type=Listing.TYPE_WISH, kind=Listing.KIND_OTHER, title="Help moving a sofa")
    _client(person).post(reverse("gift_circles:bring", args=[event.slug]), {"listing": wish.pk})
    _client(person).get(_url(event))
    entry = Entry.objects.get()
    assert (entry.text, entry.from_user, entry.listing, entry.type) == ("Help moving a sofa", person, wish, "wish")

    offer = Listing.objects.create(owner=person, type=Listing.TYPE_OFFER, kind=Listing.KIND_OTHER, title="Apple tree cuttings")
    _client(person).post(reverse("gift_circles:bring", args=[event.slug]), {"listing": offer.pk})
    assert event.entries.filter(listing=offer).exists()

    _client(person).post(reverse("gift_circles:take_back", args=[event.slug, offer.pk]))
    assert not event.entries.filter(listing=offer).exists()
    # Opening it again doesn't add it twice
    _client(person).get(_url(event))
    assert event.entries.count() == 1


def test_who_comes_adds_their_own_lines_and_takes_them_back(host, person, stranger):
    event = _circle(host)
    _come(event, person)
    response = _add(person, event, "A ride to Lübeck", who="new", name="Someone")
    assert response.status_code == 302
    entry = Entry.objects.get()
    # Not the scribe: the line is their own, whatever the picker says
    assert (entry.from_user, entry.from_name, entry.created_by) == (person, "", person)
    _add(stranger, event, "Not allowed")
    assert Entry.objects.count() == 1

    _client(person).post(_entry_url(event, entry), {"action": "delete"})
    assert not Entry.objects.exists()


def test_the_scribe_writes_for_anyone_and_answers_lines(host, person, other):
    event = _circle(host)
    _come(event, person)
    _come(event, other)
    _client(host).post(reverse("gift_circles:scribe", args=[event.slug]), {"user": person.pk, "action": "make"})
    assert Scribe.objects.filter(event=event, user=person).exists()
    assert "No longer scribe" in _client(host).get(event.get_absolute_url()).content.decode()

    _add(person, event, "Help moving a sofa", who=f"user:{other.pk}")
    entry = Entry.objects.get()
    assert (entry.from_user, entry.created_by) == (other, person)

    # Not to the one it is from
    _client(person).post(_entry_url(event, entry), {"action": "fulfilled", "who": f"user:{other.pk}"})
    entry.refresh_from_db()
    assert entry.state == Entry.STATE_OPEN

    _client(person).post(_entry_url(event, entry), {"action": "fulfilled", "who": f"user:{host.pk}"})
    entry.refresh_from_db()
    assert (entry.state, entry.for_user) == (Entry.STATE_FULFILLED, host)
    assert "Fulfilled by Mira" in _client(other).get(_url(event)).content.decode()

    # Ideas: several, from several people, each saying what it is
    _client(person).post(_entry_url(event, entry), {"action": "idea", "who": "new", "name": "Theo", "idea": "Ask the repair café"})
    _client(person).post(_entry_url(event, entry), {"action": "idea", "who": f"user:{host.pk}", "idea": "A cargo bike"})
    _client(person).post(_entry_url(event, entry), {"action": "idea", "who": f"user:{host.pk}", "idea": ""})
    assert [(idea.from_label, idea.text) for idea in entry.ideas.all()] == [("Theo", "Ask the repair café"), ("Mira", "A cargo bike")]
    page = _client(other).get(_url(event)).content.decode()
    assert "An idea from Theo: Ask the repair café" in page and "An idea from Mira: A cargo bike" in page
    _client(person).post(_entry_url(event, entry), {"action": "idea_delete", "idea": entry.ideas.last().pk})
    assert entry.ideas.count() == 1

    _client(person).post(_entry_url(event, entry), {"action": "open"})
    entry.refresh_from_db()
    assert (entry.state, entry.for_name) == (Entry.STATE_OPEN, "")

    # Someone else can't answer it or take back someone else's line
    _client(other).post(_entry_url(event, entry), {"action": "fulfilled", "who": f"user:{host.pk}"})
    _client(other).post(_entry_url(event, entry), {"action": "delete"})
    entry.refresh_from_db()
    assert entry.state == Entry.STATE_OPEN

    _client(host).post(reverse("gift_circles:scribe", args=[event.slug]), {"user": person.pk, "action": "remove"})
    assert not Scribe.objects.exists()


def test_only_who_comes_becomes_scribe(host, stranger):
    event = _circle(host)
    _client(host).post(reverse("gift_circles:scribe", args=[event.slug]), {"user": stranger.pk})
    assert not Scribe.objects.exists()


def test_the_picker_lists_who_comes_guests_and_who_was_invited(host, person):
    event = _circle(host)
    _come(event, person)
    guest = _guest(event)
    invitation = Invitation.objects.create(event=event, invited_by=host, email="theo.k@example.com")
    people = dict(sheets.people(event))
    assert people[f"user:{host.pk}"] == "Mira"
    assert people[f"user:{person.pk}"] == "Tomek"
    assert people[f"guest:{guest.pk}"] == "Lena"
    # Never the whole address
    assert people[f"invitation:{invitation.pk}"] == "theo.k"


def test_a_walk_in_with_an_email_comes_as_a_guest_without_a_mail(host):
    event = _circle(host)
    _add(host, event, "A box of jam jars", type="offer", who="new", name="Theo", email="theo@example.com")
    guest = Guest.objects.get()
    assert (guest.name, guest.added_by) == ("Theo", host)
    assert guest.confirmed_at is not None
    assert Entry.objects.get().from_guest == guest
    assert mail.outbox == []
    assert emails_left(event) == EMAIL_LIMIT - 1
    # They can create an account through their link like any guest
    assert _client().get(reverse("gift_circles:guest_account", args=[event.slug, guest.token])).status_code == 302


def test_an_invited_address_picked_becomes_a_guest(host):
    event = _circle(host)
    invitation = Invitation.objects.create(event=event, invited_by=host, name="Theo", email="theo@example.com")
    _add(host, event, "Seeds of beans", type="offer", who=f"invitation:{invitation.pk}")
    assert not Invitation.objects.exists()
    assert Entry.objects.get().from_guest.email == "theo@example.com"
    assert emails_left(event) == EMAIL_LIMIT - 1


def test_no_more_walk_in_addresses_than_the_limit(host):
    event = _circle(host)
    for number in range(EMAIL_LIMIT):
        Invitation.objects.create(event=event, invited_by=host, email=f"someone{number}@example.com")
    response = _add(host, event, "A ladder", type="offer", who="new", name="Theo", email="theo@example.com")
    assert response.status_code == 200
    assert "add more email addresses" in response.content.decode()
    assert not Entry.objects.exists()
    # By name only, it goes on
    _add(host, event, "A ladder", type="offer", who="new", name="Theo")
    assert Entry.objects.get().from_name == "Theo"


def test_a_guest_adds_their_own_lines_through_their_link(host):
    event = _circle(host)
    guest = _guest(event)
    url = reverse("gift_circles:guest_giftsheet", args=[event.slug, guest.token])
    assert "Open the Giftsheet" in Client().get(reverse("gift_circles:guest", args=[event.slug, guest.token])).content.decode()
    Client().post(url, {"type": "wish", "text": "Someone to teach me to sharpen a scythe"})
    entry = Entry.objects.get()
    assert (entry.from_guest, entry.created_by) == (guest, None)
    Client().post(reverse("gift_circles:guest_giftsheet_entry", args=[event.slug, guest.token, entry.pk]), {"action": "delete"})
    assert not Entry.objects.exists()


def test_it_refreshes_from_the_start_until_it_is_closed(host):
    event = _circle(host, days=2)
    page = _client(host).get(_url(event)).content.decode()
    assert "hx-get" not in page

    event = _circle(host, days=-1, title="Yesterday's gift-circle")
    page = _client(host).get(_url(event)).content.decode()
    assert "every 5s" in page
    # The lines alone for the refresh
    part = _client(host).get(_url(event), HTTP_HX_REQUEST="true").content.decode()
    assert part.lstrip().startswith("<div id=\"entries\"")

    _client(host).post(reverse("gift_circles:giftsheet_close", args=[event.slug]))
    assert "hx-get" not in _client(host).get(_url(event)).content.decode()


def test_closing_makes_offers_wishes_and_matches(host, person, other):
    event = _circle(host)
    _come(event, person, keep=True)
    _come(event, other)
    guest = _guest(event)
    # Brought: it keeps its listing; said in the circle: a new one, for who said yes
    brought = Listing.objects.create(owner=other, type=Listing.TYPE_OFFER, kind=Listing.KIND_OTHER, title="Apple tree cuttings")
    _client(other).post(reverse("gift_circles:bring", args=[event.slug]), {"listing": brought.pk})
    _add(host, event, "Help moving a sofa", who=f"user:{person.pk}")
    _add(host, event, "A ride to Lübeck", who=f"user:{person.pk}")
    _add(host, event, "Jam jars", type="offer", who=f"user:{other.pk}")
    _add(host, event, "Bike repair", type="offer", who=f"guest:{guest.pk}")
    sofa, ride, jars, bike = Entry.objects.filter(listing=None).order_by("pk")
    cuttings = Entry.objects.get(listing=brought)
    Idea.objects.create(entry=ride, from_user=other, text="Ask at the station")
    for entry, action, who in (
        (sofa, "fulfilled", f"user:{other.pk}"),
        (cuttings, "fulfilled", f"user:{person.pk}"), (bike, "fulfilled", f"user:{person.pk}"),
    ):
        _client(host).post(_entry_url(event, entry), {"action": action, "who": who})

    _client(person).post(reverse("gift_circles:giftsheet_close", args=[event.slug]))
    assert event.giftsheet.closed_at is None
    _client(host).post(reverse("gift_circles:giftsheet_close", args=[event.slug]))
    event.giftsheet.refresh_from_db()
    assert event.giftsheet.is_closed
    for entry in (sofa, ride, jars, bike, cuttings):
        entry.refresh_from_db()

    # Tomek said yes: his lines are on ecobasa now
    assert sofa.listing.owner == person and sofa.listing.title == "Help moving a sofa" and sofa.listing.is_wish
    assert ride.listing.owner == person
    # Ayla didn't, and a guest stays a line
    assert jars.listing is None and bike.listing is None
    # Fulfilled between two account holders: accepted at once, on the listing
    assert sofa.match.status == Match.STATUS_ACCEPTED
    assert (sofa.match.from_user, sofa.match.recipient, sofa.match.target) == (other, person, sofa.listing)
    # A fulfilled wish is met: no longer current
    assert sofa.listing.status == Listing.STATUS_COVERED
    assert cuttings.listing == brought and (cuttings.match.from_user, cuttings.match.recipient) == (person, other)
    # An idea, or no listing: no match
    assert ride.match is None and bike.match is None
    assert Match.objects.filter(content_type__model="listing").count() == 2
    assert mail.outbox == []

    # Closed, nothing changes; opened again and closed, nothing is made twice
    _add(person, event, "Too late")
    assert not Entry.objects.filter(text="Too late").exists()
    _client(host).post(reverse("gift_circles:giftsheet_close", args=[event.slug]), {"action": "reopen"})
    _client(host).post(reverse("gift_circles:giftsheet_close", args=[event.slug]))
    assert Listing.objects.filter(owner=person).count() == 2
    assert Match.objects.filter(content_type__model="listing").count() == 2


def test_the_host_says_whether_their_own_lines_stay_on_ecobasa(host):
    event = _circle(host)
    _client(host).post(reverse("gift_circles:attendee", args=[event.slug]), {"keep_on_ecobasa": "on", "next": _url(event)})
    assert Attendee.objects.get(event=event, user=host).keep_on_ecobasa


def _photo():
    from PIL import Image

    data = BytesIO()
    Image.new("RGB", (40, 30), "white").save(data, "JPEG")
    return SimpleUploadedFile("giftsheet.jpg", data.getvalue(), content_type="image/jpeg")


def test_up_to_two_photos_of_the_paper_giftsheet(host, person, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    event = _circle(host)
    _come(event, person)
    url = reverse("gift_circles:giftsheet_photo", args=[event.slug])
    _client(person).post(url, {"image": _photo()})
    assert not GiftsheetPhoto.objects.exists()
    for _ in range(3):
        _client(host).post(url, {"image": _photo()})
    assert GiftsheetPhoto.objects.count() == 2
    assert "Photos of the Giftsheet" in _client(person).get(_url(event)).content.decode()
    photo = GiftsheetPhoto.objects.first()
    _client(host).post(reverse("gift_circles:giftsheet_photo_delete", args=[event.slug, photo.pk]))
    assert GiftsheetPhoto.objects.count() == 1


def test_who_came_by_name_is_on_the_list_after(host):
    event = _circle(host)
    _add(host, event, "A ladder", type="offer", who="new", name="Theo")
    assert dict(sheets.people(event))["name:Theo"] == "Theo"
    _add(host, event, "Help with the garden", who="name:Theo")
    assert [entry.from_name for entry in Entry.objects.all()] == ["Theo", "Theo"]


def test_lines_are_edited_by_the_scribe_and_by_who_wrote_them(host, person, other):
    event = _circle(host)
    _come(event, person)
    _come(event, other)
    _add(person, event, "A ride to Lubeck")
    entry = Entry.objects.get()
    _client(person).post(_entry_url(event, entry), {"action": "edit", "text": "A ride to Lübeck", "type": "offer"})
    entry.refresh_from_db()
    assert (entry.text, entry.type) == ("A ride to Lübeck", "offer")
    # Someone else's line: no
    _client(other).post(_entry_url(event, entry), {"action": "edit", "text": "Mine now"})
    entry.refresh_from_db()
    assert entry.text == "A ride to Lübeck"
    # The host changes whom it is from too
    _client(host).post(_entry_url(event, entry), {"action": "edit", "text": "A ride to Lübeck", "type": "wish", "who": f"user:{other.pk}"})
    entry.refresh_from_db()
    assert (entry.type, entry.from_user) == ("wish", other)


def test_a_brought_line_keeps_its_kind_and_person(host, person):
    event = _circle(host)
    _come(event, person)
    wish = Listing.objects.create(owner=person, type=Listing.TYPE_WISH, kind=Listing.KIND_OTHER, title="Help moving a sofa")
    _client(person).post(reverse("gift_circles:bring", args=[event.slug]), {"listing": wish.pk})
    _client(host).get(_url(event))
    entry = Entry.objects.get()
    _client(host).post(_entry_url(event, entry), {"action": "edit", "text": "Help moving a big sofa", "type": "offer", "who": f"user:{host.pk}"})
    entry.refresh_from_db()
    assert (entry.text, entry.type, entry.from_user) == ("Help moving a big sofa", "wish", person)


def test_the_printed_giftsheet_is_filled_in_for_who_may_see_it(host, person, stranger):
    event = _circle(host)
    _come(event, person)
    _add(host, event, "Help moving a sofa", who="new", name="Theo", email="theo@example.com")
    entry = Entry.objects.get()
    Idea.objects.create(entry=entry, from_name="Lena", text="Ask the neighbours")
    url = reverse("gift_circles:print", args=[event.slug])
    page = _client(person).get(url).content.decode()
    assert "Help moving a sofa" in page and "An idea from Lena: Ask the neighbours" in page
    # Names only
    assert "theo@example.com" not in page
    assert "Help moving a sofa" not in _client(stranger).get(url).content.decode()
    guest = Guest.objects.get()
    page = Client().get(reverse("gift_circles:guest_print", args=[event.slug, guest.token])).content.decode()
    assert "Help moving a sofa" in page


def test_the_printed_giftsheet_runs_over_more_pages(host):
    from gift_economy.gift_circles.views import GIFTSHEET_ROWS, _pages

    front, back = GIFTSHEET_ROWS
    assert [len(page) for page in _pages([])] == [front, back]
    pages = _pages(list(range(front + back + 1)))
    assert [len(page) for page in pages] == [front, back, back]
    assert pages[2][0] == front + back and pages[2][1] is None
