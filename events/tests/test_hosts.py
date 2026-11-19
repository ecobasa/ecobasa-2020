"""Events hosted by a person or a tour, at a place of their own or online, with a limit of
people, and kinds with an address of their own."""
from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from communities.models import Community, Membership
from gift_economy.matches.models import Match, StayDetails
from tours.models import Stop, Tour, append_stop
from users.models import User

from .. import kinds
from ..models import Event
from ..zones import zone_at

pytestmark = pytest.mark.django_db

PARK = Point(9.18, 48.78, srid=4326)
PARK_ADDRESS = "Lindenallee 12, 70173 Stuttgart, Deutschland"


@pytest.fixture
def host():
    return User.objects.create_user(email="mira@example.com", password="secret", name="Mira")


@pytest.fixture
def guest():
    return User.objects.create_user(email="tomek@example.com", password="secret", name="Tomek")


@pytest.fixture
def community():
    ambassador = User.objects.create_user(email="ivo@example.com", password="secret", name="Ivo")
    return Community.objects.create(name="Wiesengrund", ambassador=ambassador)


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _circle(**fields):
    today = timezone.localdate()
    fields.setdefault("title", "Gift-circle in the park")
    fields.setdefault("starts_on", today + timedelta(days=7))
    fields.setdefault("ends_on", fields["starts_on"])
    if not fields.get("is_online") and "location" not in fields:
        fields.update(location=PARK, location_name=PARK_ADDRESS)
    return Event.objects.create(kind=kinds.GIFT_CIRCLE, is_open=True, **fields)


def _come(event, user, people=1):
    match = Match(from_user=user, recipient=event.manager, message="", status=Match.STATUS_ACCEPTED)
    match.target = event
    match.save()
    StayDetails.objects.create(match=match, volunteer_mode=StayDetails.MODE_COME, people=people)
    return match


# ── Hosts ───────────────────────────────────────────────────────────

def test_a_person_invites_to_a_gift_circle_at_its_own_address(host):
    day = timezone.localdate() + timedelta(days=3)
    response = _client(host).post(reverse("events:gift_circle_create"), {
        "kind": kinds.GIFT_CIRCLE, "title": "Gift-circle in the park", "starts_on": day, "ends_on": day,
        "location_name": PARK_ADDRESS, "location": "SRID=4326;POINT (9.18 48.78)", "is_open": "on",
    })
    event = Event.objects.get()
    assert response.status_code == 302 and response.url == f"/gift-circles/{event.slug}/"
    assert (event.host_user, event.community, event.manager, event.host) == (host, None, host, host)
    assert event.can_edit(host)
    assert _client(host).get(event.get_absolute_url()).status_code == 200


def test_a_person_only_hosts_kinds_that_allow_it(host):
    form = _client(host).get(reverse("events:gift_circle_create")).context["form"]
    assert [value for value, _label in form.fields["kind"].choices] == [kinds.GIFT_CIRCLE]
    # Projects and community events are a community's: no address of their own to start one
    assert all(kind in kinds.ADDRESSES for kind, hosts in kinds.HOSTS.items() if kinds.HOST_PERSON in hosts)
    assert kinds.PROJECT not in kinds.ADDRESSES


def test_a_person_s_event_needs_a_place_or_to_be_online(host):
    day = timezone.localdate() + timedelta(days=3)
    data = {"kind": kinds.GIFT_CIRCLE, "title": "Circle", "starts_on": day, "ends_on": day}
    response = _client(host).post(reverse("events:gift_circle_create"), data)
    assert response.status_code == 200 and response.context["form"].errors["location_name"]
    _client(host).post(reverse("events:gift_circle_create"), {**data, "is_online": "on"})
    event = Event.objects.get()
    assert event.is_online and event.place is None and event.rough_place() == ("", None)


def test_an_online_event_has_a_timezone_one_at_a_place_none(host):
    day = timezone.localdate() + timedelta(days=3)
    data = {"kind": kinds.GIFT_CIRCLE, "title": "Circle", "starts_on": day, "ends_on": day, "is_online": "on"}
    response = _client(host).post(reverse("events:gift_circle_create"), {**data, "timezone": "Mars/Olympus_Mons"})
    assert response.context["form"].errors["timezone"]
    _client(host).post(reverse("events:gift_circle_create"), {**data, "timezone": "America/Mexico_City"})
    event = Event.objects.get()
    assert event.timezone == "America/Mexico_City" and event.zone_city == "Mexico City"
    data.pop("is_online")
    _client(host).post(reverse("events:gift_circle_edit", args=[event.slug]), {
        **data, "timezone": "America/Mexico_City", "location_name": PARK_ADDRESS, "location": "SRID=4326;POINT (9.18 48.78)",
    })
    event.refresh_from_db()
    assert event.timezone == "" and event.zone is None


def test_an_online_event_says_its_languages_one_at_a_place_none(host):
    day = timezone.localdate() + timedelta(days=3)
    data = {"kind": kinds.GIFT_CIRCLE, "title": "Circle", "starts_on": day, "ends_on": day, "is_online": "on"}
    response = _client(host).post(reverse("events:gift_circle_create"), {**data, "languages": "de,xx"})
    assert response.context["form"].errors["languages"]
    _client(host).post(reverse("events:gift_circle_create"), {**data, "languages": "de,it"})
    event = Event.objects.get()
    assert event.languages == ["de", "it"] and event.language_names == "German, Italian"
    assert "German, Italian" in _client(host).get(event.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    data.pop("is_online")
    _client(host).post(reverse("events:gift_circle_edit", args=[event.slug]), {
        **data, "languages": "de", "location_name": PARK_ADDRESS, "location": "SRID=4326;POINT (9.18 48.78)",
    })
    event.refresh_from_db()
    assert event.languages == []


def test_the_timezone_nearest_a_place():
    # Near a border its country decides
    assert zone_at(PARK) == "Europe/Zurich" and zone_at(PARK, "DE") == "Europe/Berlin"
    assert zone_at(Point(-99.13, 19.43, srid=4326)) == "America/Mexico_City"
    assert zone_at(Point(-58.38, -34.6, srid=4326)) == "America/Argentina/Buenos_Aires"
    assert zone_at(Point(151.2, -33.87, srid=4326)) == "Australia/Sydney"
    # Cancun's clock isn't Mexico City's
    assert zone_at(Point(-86.85, 21.16, srid=4326)) == "America/Cancun"
    assert zone_at(None) is None


def test_the_timezone_starts_as_the_event_s_else_its_host_s_else_the_browser_s(host):
    url = reverse("events:gift_circle_create")
    form = _client(host).get(url).context["form"]
    # Any of the browser's
    assert form.browser_zones == [] and form.initial["timezone"] == "Europe/Berlin"
    host.location, host.country = PARK, "DE"
    host.save()
    form = _client(host).get(url).context["form"]
    assert form.browser_zones is None and form.initial["timezone"] == "Europe/Berlin"
    # Where the country has several clocks, the browser's if it is one of them
    host.location, host.country = Point(-96.8, 32.8, srid=4326), "US"
    host.save()
    form = _client(host).get(url).context["form"]
    assert "America/Chicago" in form.browser_zones and "Europe/Berlin" not in form.browser_zones
    assert b'id="browser-zones"' in _client(host).get(url).content
    event = _circle(host_user=host, is_online=True, timezone="Asia/Tokyo")
    form = _client(host).get(reverse("events:gift_circle_edit", args=[event.slug])).context["form"]
    assert form.initial["timezone"] == "Asia/Tokyo" and form.browser_zones is None


def test_a_person_s_event_asks_nothing_only_a_community_s_does(host):
    form = _client(host).get(reverse("events:gift_circle_create")).context["form"]
    assert not {"skills_to_learn", "volunteers_wanted", "food_provided"} & set(form.fields)
    assert _client(host).get(reverse("events:gift_circle_create")).context["formset"] is None


def test_a_gift_circle_happens_on_one_day(host):
    day = timezone.localdate() + timedelta(days=3)
    data = {"kind": kinds.GIFT_CIRCLE, "title": "Circle", "is_online": "on"}
    response = _client(host).post(reverse("events:gift_circle_create"), data)
    assert response.context["form"].errors["starts_on"]
    _client(host).post(reverse("events:gift_circle_create"), {**data, "starts_on": day, "ends_on": day + timedelta(days=5)})
    event = Event.objects.get()
    assert (event.starts_on, event.ends_on) == (day, day) and not event.is_ongoing


def test_a_gift_circle_saved_without_an_end_ends_the_day_it_starts(host):
    event = _circle(host_user=host, ends_on=None)
    assert event.ends_on == event.starts_on and not event.is_ongoing


def test_an_event_has_exactly_one_host(host, community):
    with pytest.raises(IntegrityError), transaction.atomic():
        _circle(host_user=host, community=community)
    with pytest.raises(IntegrityError), transaction.atomic():
        _circle()


def test_strangers_cannot_edit_a_person_s_event(host, guest):
    event = _circle(host_user=host)
    assert not event.can_edit(guest)
    assert _client(guest).get(event.url("edit")).status_code == 403


# ── Addresses ───────────────────────────────────────────────────────

def test_gift_circles_live_at_their_own_address_whoever_hosts_them(host, community):
    mine = _circle(host_user=host)
    theirs = _circle(community=community)
    assert mine.slug != theirs.slug
    assert theirs.get_absolute_url() == f"/gift-circles/{theirs.slug}/"
    assert Client().get(theirs.get_absolute_url()).status_code == 200
    # Not under the community as well
    assert Client().get(f"/communities/{community.slug}/events/{theirs.slug}/").status_code == 404


def test_a_slug_can_repeat_across_addresses(host, community):
    project = Event.objects.create(community=community, title="Gift-circle in the park")
    circle = _circle(host_user=host)
    assert project.slug == circle.slug == "gift-circle-in-the-park"
    assert project.get_absolute_url() != circle.get_absolute_url()


def test_a_project_becoming_a_gift_circle_gets_a_free_slug(host, community):
    _circle(host_user=host, title="Open day")
    event = Event.objects.create(community=community, title="Open day", kind=kinds.COMMUNITY_EVENT)
    event.kind = kinds.GIFT_CIRCLE
    event.save()
    assert event.slug == "open-day-2"


# ── Where ───────────────────────────────────────────────────────────

def test_a_place_of_its_own_is_rough_for_everyone_but_the_host_and_who_comes(host, guest):
    event = _circle(host_user=host)
    stranger = User.objects.create_user(email="ola@example.com", password="secret")
    name, point = event.rough_place()
    assert name == "Stuttgart, Deutschland" and point != PARK
    assert event.place_for(host) == (PARK_ADDRESS, PARK)
    assert event.place_for(stranger)[0] == "Stuttgart, Deutschland"
    page = Client().get(event.get_absolute_url()).content.decode()
    assert "Lindenallee" not in page
    _come(event, guest)
    assert event.place_for(guest) == (PARK_ADDRESS, PARK)
    assert "Lindenallee" in _client(guest).get(event.get_absolute_url()).content.decode()


def test_a_community_s_event_is_at_its_place_unless_it_has_one_of_its_own(community):
    community.location, community.location_name = Point(10.0, 50.0, srid=4326), "Wiesengrund 1, Dorf"
    community.save()
    event = Event.objects.create(community=community, title="Open day", kind=kinds.COMMUNITY_EVENT)
    assert event.place == community
    event.location, event.location_name = PARK, PARK_ADDRESS
    assert event.place is event


def test_online_events_are_listed_but_not_on_the_map(host):
    event = _circle(host_user=host, is_online=True)
    markers = Client().get(reverse("events:api-markers")).json()["features"]
    assert markers == []
    listed = Client().get(reverse("events:api-list")).context["events"]
    assert listed == [event]
    assert "Online" in Client().get(event.get_absolute_url()).content.decode()


def test_a_place_of_its_own_shows_roughly_on_the_map(host):
    _circle(host_user=host)
    [marker] = Client().get(reverse("events:api-markers")).json()["features"]
    assert marker["geometry"]["coordinates"] != [PARK.x, PARK.y]


# ── How many can come ───────────────────────────────────────────────

def test_a_full_event_takes_nobody_more(host, guest):
    event = _circle(host_user=host, max_people=3)
    _come(event, User.objects.create_user(email="ruth@example.com", password="secret"), people=2)
    assert event.free_places() == 1 and event.takes_people(guest)
    response = _client(guest).post(event.url("come"), {"people": "2"})
    assert response.status_code == 302 and not event.matches.filter(from_user=guest).exists()
    _client(guest).post(event.url("come"), {"people": "1"})
    assert event.matches.filter(from_user=guest).exists()
    assert event.free_places() == 0 and not event.takes_people()


def test_without_a_limit_there_is_always_room(host):
    event = _circle(host_user=host)
    assert event.free_places() is None and event.takes_people()


# ── A tour's gift-circle ────────────────────────────────────────────

@pytest.fixture
def tour(host):
    return Tour.objects.create(title="Seeds along the river", organiser=host)


def test_a_tour_invites_to_a_gift_circle_at_a_stop(tour, host):
    day = timezone.localdate() + timedelta(days=10)
    stop = Stop(tour=tour, name="Market square, Esslingen", location=PARK, arrive_on=day)
    append_stop(stop)
    url = reverse("tours:stop_gift_circle", args=[tour.slug, stop.pk])
    form = _client(host).get(url).context["form"]
    assert (form.instance.starts_on, form.instance.location_name) == (day, stop.name)
    _client(host).post(url, {
        "kind": kinds.GIFT_CIRCLE, "title": "Gift-circle on the market square", "starts_on": day, "ends_on": day,
        "location_name": stop.name, "location": "SRID=4326;POINT (9.18 48.78)", "is_open": "on",
    })
    event = Event.objects.get()
    stop.refresh_from_db()
    assert (event.host_tour, event.manager, stop.event, stop.community) == (tour, host, event, None)
    assert not stop.can_host_gift_circle
    # Once there is one, no second
    assert _client(host).get(url).status_code == 404


def test_only_organisers_invite_from_a_stop(tour, guest):
    stop = Stop(tour=tour, name="Market square, Esslingen", location=PARK)
    append_stop(stop)
    assert _client(guest).get(reverse("tours:stop_gift_circle", args=[tour.slug, stop.pk])).status_code == 403


def test_a_tour_s_organisers_edit_its_gift_circle(tour, host, guest):
    event = _circle(host_tour=tour)
    assert event.can_edit(host) and not event.can_edit(guest)
    assert event.host_name == "Seeds along the river"


# ── The dashboard ───────────────────────────────────────────────────

def test_one_s_own_gift_circles_are_among_the_events_one_goes_to(host):
    event = _circle(host_user=host)
    response = _client(host).get(reverse("events:going"))
    assert list(response.context["page"]) == [event]
    assert reverse("events:gift_circle_create") in response.content.decode()


def test_the_user_menu_lists_events_once_one_hosts_one(host):
    link = f'href="{reverse("events:going")}"'
    assert link not in _client(host).get("/").content.decode()
    _circle(host_user=host)
    assert link in _client(host).get("/").content.decode()


def test_the_cards_say_how_many_come(host, guest):
    from gift_economy.gift_circles.models import Guest

    event = _circle(host_user=host, max_people=12)
    _come(event, guest, people=2)
    Guest.objects.create(event=event, name="Ayla", email="ayla@example.com", confirmed_at=timezone.now())
    Guest.objects.create(event=event, name="Theo", email="theo@example.com")
    for page in (_client(host).get(reverse("events:going")), Client().get(reverse("events:api-list"))):
        assert "3 people so far · Room for 12 people" in page.content.decode()
    [marker] = Client().get(reverse("events:api-markers")).json()["features"]
    assert marker["properties"]["coming"] == "3 people so far · Room for 12 people"


def test_the_map_offers_gift_circles_to_everyone_and_more_to_ambassadors(host, community):
    response = _client(host).get(reverse("events:list"))
    assert [url for url, _label, _icon in response.context["create_buttons"]] == [reverse("events:gift_circle_create")]
    response = _client(community.ambassador).get(reverse("events:list"))
    urls = [url for url, _label, _icon in response.context["create_buttons"]]
    create = reverse("events:create", args=[community.slug])
    assert urls == [
        reverse("events:gift_circle_create"), f"{create}?kind={kinds.PROJECT}", f"{create}?kind={kinds.COMMUNITY_EVENT}",
    ]
    assert _client(community.ambassador).get(urls[1]).status_code == 200


def test_members_invite_to_their_community_s_events(guest, community):
    Membership.objects.create(community=community, user=guest, stage=Membership.STAGE_MEMBER)
    urls = [url for url, _label, _icon in _client(guest).get(reverse("events:list")).context["create_buttons"]]
    create = reverse("events:create", args=[community.slug])
    assert f"{create}?kind={kinds.PROJECT}" in urls
    day = timezone.localdate() + timedelta(days=4)
    _client(guest).post(f"{create}?kind={kinds.COMMUNITY_EVENT}", {
        "kind": kinds.COMMUNITY_EVENT, "title": "Open day", "starts_on": day, "ends_on": day, "is_open": "on",
        "needs-TOTAL_FORMS": "0", "needs-INITIAL_FORMS": "0",
    })
    event = Event.objects.get()
    assert event.community == community and event.manager == community.ambassador and event.can_edit(guest)
    # The community's calendar stays the ambassador's
    page = _client(guest).get(event.get_absolute_url()).content.decode()
    assert reverse("matches:calendar", args=[community.slug]) not in page


# ── Deleting ────────────────────────────────────────────────────────

def test_the_host_deletes_a_gift_circle_with_who_comes(host, guest):
    event = _circle(host_user=host)
    _come(event, guest)
    edit_page = _client(host).get(event.url("edit")).content.decode()
    assert event.url("delete") in edit_page
    assert _client(guest).post(event.url("delete")).status_code == 403
    response = _client(host).post(event.url("delete"))
    assert response.status_code == 302 and response.url == host.get_absolute_url()
    assert not Event.objects.exists() and not Match.objects.exists()


def test_a_deleted_gift_circle_leaves_its_tour_s_stop(tour, host):
    event = _circle(host_tour=tour)
    stop = Stop(tour=tour, name="Market square, Esslingen", location=PARK, arrive_on=event.starts_on, event=event)
    append_stop(stop)
    _client(host).post(event.url("delete"))
    stop.refresh_from_db()
    assert stop.event is None


# ── Profiles ────────────────────────────────────────────────────────

def test_a_profile_lists_the_gift_circles_one_hosts_and_comes_to(host, guest, community):
    today = timezone.localdate()
    hosted = _circle(host_user=host, title="In the park")
    came = _circle(host_user=guest, title="At Tomek's", starts_on=today - timedelta(days=30))
    _come(came, host)
    _circle(host_user=guest, title="Not coming")
    project = Event.objects.create(kind=kinds.PROJECT, community=community, title="Straw-bale wall")
    _come(project, host)
    response = _client(guest).get(host.get_absolute_url())
    page = response.content.decode()
    assert [(e, e.hosted) for e in response.context["events"]] == [(hosted, True), (came, False)]
    assert "Not coming" not in page and "Straw-bale wall" not in page
    # Where it is shows on its page
    assert PARK_ADDRESS not in page


def test_a_profile_lists_only_the_latest_past_gift_circles(host):
    today = timezone.localdate()
    for weeks in range(1, 8):
        _circle(host_user=host, title=f"{weeks} weeks ago", starts_on=today - timedelta(weeks=weeks))
    response = _client(host).get(host.get_absolute_url())
    assert [e.title for e in response.context["events"]] == [f"{weeks} weeks ago" for weeks in range(1, 6)]


# ── Its picture ─────────────────────────────────────────────────────

def test_a_picture_is_shrunk_to_what_a_page_needs(host, settings, tmp_path):
    import io
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings.MEDIA_ROOT = tmp_path
    out = io.BytesIO()
    Image.new("RGB", (4000, 3000), "orange").save(out, "PNG")
    day = timezone.localdate() + timedelta(days=3)
    _client(host).post(reverse("events:gift_circle_create"), {
        "kind": kinds.GIFT_CIRCLE, "title": "Circle", "starts_on": day, "is_online": "on",
        "image": SimpleUploadedFile("park.png", out.getvalue(), content_type="image/png"),
    })
    event = Event.objects.get()
    assert event.image.name.endswith(".jpg")
    with Image.open(event.image.path) as image:
        assert max(image.size) == 1600
    assert 'View fullscreen' in _client(host).get(event.get_absolute_url()).content.decode()
