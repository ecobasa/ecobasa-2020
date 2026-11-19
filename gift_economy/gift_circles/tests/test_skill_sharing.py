"""Online skill-sharing: a skill or knowledge both can share from afar is suggested however
far apart they live; from the suggestion one of them starts an online gift-circle for it;
everyone else who shares it from afar hears about the circle."""
from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events import kinds
from events.models import Event
from gift_economy.gift_circles.models import Brought, Invitation
from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import Skill
from gift_economy.matches.matching import match
from gift_economy.matches.models import Suggestion
from users.models import User

pytestmark = pytest.mark.django_db

STUTTGART = Point(9.18, 48.78, srid=4326)
LISBON = Point(-9.14, 38.72, srid=4326)
OSLO = Point(10.75, 59.91, srid=4326)


def _user(email, name, location):
    return User.objects.create_user(email=email, password="secret", name=name, location=location)


@pytest.fixture
def mira():
    return _user("mira@example.com", "Mira", STUTTGART)


@pytest.fixture
def tomek():
    return _user("tomek@example.com", "Tomek", LISBON)


@pytest.fixture
def ayla():
    return _user("ayla@example.com", "Ayla", OSLO)


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _skill(owner, type, name, **fields):
    skill = Skill.objects.get_or_create(name=name)[0]
    return Listing.objects.create(owner=owner, type=type, kind=Listing.KIND_SKILL, skill=skill, **fields)


def test_a_skill_both_share_from_afar_is_suggested_however_far_apart(mira, tomek):
    offer = _skill(mira, Listing.TYPE_OFFER, "Spanish", from_afar=True)
    wish = _skill(tomek, Listing.TYPE_WISH, "Spanish")
    # Only one of them from afar: too far
    assert match(wish, notify=False) == []
    wish.from_afar = True
    wish.save()
    found = match(wish, notify=False)
    assert {suggestion.user for suggestion in found} == {mira, tomek}
    suggestion = Suggestion.objects.get(user=tomek)
    assert suggestion.from_afar and suggestion.starts_skill_sharing and suggestion.other == offer


def test_helping_hands_are_never_from_afar(mira):
    response = _client(mira).post(reverse("gifts:create"), {
        "type": "offer", "kind": "hands", "title": "Moving furniture", "from_afar": "on",
    })
    assert response.status_code == 302
    assert Listing.objects.get().from_afar is False


def test_new_knowledge_starts_from_afar(mira):
    form = _client(mira).get(f"{reverse('gifts:create')}?kind=knowledge").context["form"]
    assert form["from_afar"].value() is True
    form = _client(mira).get(f"{reverse('gifts:create')}?kind=skill").context["form"]
    assert not form["from_afar"].value()


def test_one_starts_an_online_skill_sharing_from_the_suggestion(
    mira, tomek, ayla, django_capture_on_commit_callbacks,
):
    offers = [_skill(mira, Listing.TYPE_OFFER, name, from_afar=True) for name in ("Spanish", "Guitar")]
    with django_capture_on_commit_callbacks(execute=True):
        for name in ("Spanish", "Guitar"):
            _skill(tomek, Listing.TYPE_WISH, name, from_afar=True)
    suggestion = Suggestion.objects.filter(user=mira).first()
    page = _client(mira).get(reverse("matches:list")).content.decode()
    assert "Start an online skill-sharing" in page and "Also from afar" in page

    url = f"{reverse('events:gift_circle_create')}?suggestion={suggestion.pk}"
    form = _client(mira).get(url).context["form"]
    assert form["is_online"].value() is True
    assert form["title"].value() in ("Online skill-sharing: Spanish, Guitar", "Online skill-sharing: Guitar, Spanish")

    # Ayla, far away, wishes to learn Spanish from afar too
    ayla_s = _skill(ayla, Listing.TYPE_WISH, "Spanish", from_afar=True)
    day = timezone.localdate() + timedelta(days=5)
    with django_capture_on_commit_callbacks(execute=True):
        _client(mira).post(url, {
            "kind": kinds.GIFT_CIRCLE, "title": form["title"].value(), "starts_on": day, "ends_on": day,
            "is_online": "on", "timezone": "Europe/Berlin", "is_open": "on",
        })
    event = Event.objects.get()
    assert event.is_online and event.host_user == mira
    assert {row.listing for row in Brought.objects.filter(event=event)} == set(offers)
    assert Invitation.objects.get(event=event).user == tomek
    # Ayla hears about it, and the button goes to the circle
    shared = Suggestion.objects.get(user=ayla, own_id=str(ayla_s.pk))
    assert shared.reason == Suggestion.REASON_SHARED_ONLINE and shared.gift_circle == event
    assert shared.action_url == event.get_absolute_url() and not shared.starts_skill_sharing
    # Tomek is invited: he hears about it by the invitation, not as a suggestion
    assert not Suggestion.objects.filter(user=tomek, reason=Suggestion.REASON_SHARED_ONLINE).exists()


def test_someone_who_shares_it_from_afar_later_hears_about_the_circle(mira, ayla, django_capture_on_commit_callbacks):
    offer = _skill(mira, Listing.TYPE_OFFER, "Spanish", from_afar=True)
    day = timezone.localdate() + timedelta(days=5)
    event = Event.objects.create(
        kind=kinds.GIFT_CIRCLE, host_user=mira, title="Online skill-sharing: Spanish", is_online=True,
        starts_on=day, ends_on=day, timezone="Europe/Berlin",
    )
    Brought.objects.create(event=event, listing=offer)
    with django_capture_on_commit_callbacks(execute=True):
        wish = _skill(ayla, Listing.TYPE_WISH, "Spanish", from_afar=True)
    shared = Suggestion.objects.get(user=ayla, own_id=str(wish.pk))
    assert shared.reason == Suggestion.REASON_SHARED_ONLINE and shared.gift_circle == event


def test_only_one_s_own_suggestion_of_a_skill_from_afar_starts_one(mira, tomek):
    _skill(mira, Listing.TYPE_OFFER, "Spanish", from_afar=True)
    _skill(tomek, Listing.TYPE_WISH, "Spanish", from_afar=True)
    match(Listing.objects.get(owner=tomek), notify=False)
    tomek_s = Suggestion.objects.get(user=tomek)
    form = _client(mira).get(f"{reverse('events:gift_circle_create')}?suggestion={tomek_s.pk}").context["form"]
    assert not form["is_online"].value() and not form["title"].value()


def test_a_skill_sharing_is_agreed_on_in_the_conversation_and_asks_for_no_town(mira, tomek):
    offer = _skill(mira, Listing.TYPE_OFFER, "Spanish", from_afar=True)
    _skill(tomek, Listing.TYPE_WISH, "Spanish", from_afar=True)
    match(Listing.objects.get(owner=tomek), notify=False)
    from gift_economy.matches.models import Match
    asked = Match(from_user=tomek, recipient=mira, message="When would suit you?")
    asked.target = offer
    asked.save()
    page = _client(mira).get(asked.get_absolute_url()).content.decode()
    suggestion = Suggestion.objects.get(user=mira)
    assert f"?suggestion={suggestion.pk}" in page and "Agree on a day and time here first" in page
    response = _client(mira).get(f"{reverse('events:gift_circle_create')}?suggestion={suggestion.pk}")
    assert response.context["event"].skill_sharing


def test_one_offers_to_fulfil_a_wish_for_a_skill_online(mira, tomek):
    from gift_economy.matches.models import Match
    wish = _skill(tomek, Listing.TYPE_WISH, "Spanish", from_afar=True)
    form = _client(mira).get(wish.get_absolute_url()).context["form"]
    # From afar it starts online
    assert form["location_type"].value() == Match.LOC_ONLINE
    _client(mira).post(wish.get_absolute_url(), {
        "message": "I can teach you", "location_type": Match.LOC_ONLINE, "proposed_location": "Café Lindenblatt",
        "proposed_lat": "48.7", "proposed_lon": "9.1",
    })
    asked = Match.objects.get()
    assert asked.location_type == Match.LOC_ONLINE and asked.proposed_location == "" and asked.proposed_lat is None
    assert asked.resolved_location() == "Online, by video call or phone"
    assert asked.can_be_online


def test_a_thing_can_t_be_given_online(mira, tomek):
    from gift_economy.matches.models import Match
    wish = Listing.objects.create(owner=tomek, type=Listing.TYPE_WISH, kind=Listing.KIND_OTHER, title="A bike trailer")
    form = _client(mira).get(wish.get_absolute_url()).context["form"]
    assert Match.LOC_ONLINE not in dict(form.fields["location_type"].choices)
