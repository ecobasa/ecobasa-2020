from datetime import date, time, timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from django.test import Client
from django.urls import reverse, reverse_lazy
from django.utils import timezone, translation

from communities.models import Community
from gift_economy.gifts.models import Listing, ListingCategory
from gift_economy.matches.models import Match, MatchMessage, StayDetails
from notifications.models import Notification
from gift_economy.references.models import match_reference_subject
from gift_economy.references.reference_requests import exchange_text
from gift_economy.gifts.skills.models import Skill, SkillTaxonomy
from templatetags.site_tags import ago
from users.models import User

from gift_economy.matches.calendar import stays_of
from ..freshness import archive_stale_events, make_confirm_token
from ..models import Event
from gift_economy.gifts.models import skill_offers
from gift_economy.gifts.testing import need, skill_offer, skill_wish
from gift_economy.matches.models import Contribution


@pytest.fixture(autouse=True)
def site(settings):
    settings.SITE_URL = "https://ecobasa.test"
    settings.EVENT_STALE_DAYS = 60
    settings.EVENT_ARCHIVE_GRACE_DAYS = 14


@pytest.fixture
def ambassador():
    return User.objects.create_user(email="amb@example.com", password="secret", name="Ana", language="de")


@pytest.fixture
def helper():
    return User.objects.create_user(email="helper@example.com", password="secret", name="Hugo")


@pytest.fixture
def community(ambassador):
    return Community.objects.create(name="Sonnenhof", owner=ambassador, max_guests=2)


@pytest.fixture
def project(community):
    today = timezone.localdate()
    project = Event.objects.create(
        community=community, title="Rocket stove",
        starts_on=today + timedelta(days=5), ends_on=today + timedelta(days=40), food_provided=True,
    )
    need(project, kind=Listing.KIND_HANDS, title="Masonry", order=0)
    need(project, kind=Listing.KIND_MATERIAL, title="Clay", quantity=200, unit="kg", order=1)
    return project


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _offer(project, user, status=Match.STATUS_PENDING, needs=(), stay=(None, None)):
    match = Match(from_user=user, recipient=project.community.owner, message="Hi", status=status)
    match.target = project
    match.save()
    StayDetails.objects.create(match=match, stay_from=stay[0], stay_to=stay[1])
    for listing in needs:
        Contribution.objects.create(match=match, listing=listing)
    return match


def _aware(day):
    return timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))


def _formset(needs, prefix="needs"):
    data = {
        f"{prefix}-TOTAL_FORMS": str(len(needs)), f"{prefix}-INITIAL_FORMS": "0",
        f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for i, need in enumerate(needs):
        for key, value in need.items():
            data[f"{prefix}-{i}-{key}"] = value
    return data


# ── Creating and editing ──────────────────────────────────────────────


@pytest.mark.django_db
def test_ambassador_creates_project_with_needs_and_known_skills_are_linked(community, ambassador):
    SkillTaxonomy.objects.create(names={"en": "Carpentry", "de": "Zimmerei"})
    category = ListingCategory.objects.get(slug="building-renovation")
    response = _client(ambassador).post(reverse("events:create", args=[community.slug]), {
        "kind": "project", "title": "Guest house", "starts_on": "2030-03-01", "ends_on": "2030-04-30", "food_provided": "on",
        **_formset([
            {"kind": "hands", "title": "Zimmerei", "quantity": "2"},
            {"kind": "hands", "title": "Helping hands"},
            {"kind": "material", "title": "Straw bale", "quantity": "120", "unit": "pieces"},
            {"kind": "hands", "title": ""},  # an empty row added and left alone
        ]),
    })
    project = Event.objects.get(title="Guest house")
    assert response.status_code == 302
    assert project.created_by == ambassador
    needs = list(project.needs())
    assert [n.title for n in needs] == ["Zimmerei", "Helping hands", "Straw bale"]
    assert needs[0].skill.slug == "carpentry"
    assert needs[1].skill is None  # not in the taxonomy: plain text, no new skill
    assert needs[2].skill is None
    # Needs are the community's wishes in the project
    assert all(n.is_wish and n.community == community for n in needs)
    # People are the unit of helping hands; only things get a gift category, a material
    # that of what it is
    assert (needs[0].quantity, needs[0].unit, list(needs[0].categories.all())) == (2, "people", [])
    assert (needs[2].quantity, needs[2].unit, list(needs[2].categories.all())) == (120, "pieces", [category])
    with translation.override("en"):
        assert needs[2].amount == "120 pieces"


@pytest.mark.django_db
def test_skills_to_learn_are_listed_on_the_community(community, ambassador):
    SkillTaxonomy.objects.create(names={"en": "Clay building", "de": "Lehmbau"})
    response = _client(ambassador).post(reverse("events:create", args=[community.slug]), {
        "kind": "project", "title": "Cob oven", "skills_to_learn": "Lehmbau, Welding", **_formset([]),
    })
    assert response.status_code == 302
    project = Event.objects.get(title="Cob oven")
    assert sorted(s.skill.slug for s in project.skills_to_learn()) == ["clay-building", "welding"]
    # They are the community's skills while the project runs: it can be found (and
    # suggested) for them
    assert sorted(skill_offers(community).current().values_list("skill__slug", flat=True)) == ["clay-building", "welding"]
    page = Client().get(project.get_absolute_url()).content.decode()
    assert "What you can learn here" in page and "Welding" in page

    # Editing shows them in the editor's language
    form_page = _client(ambassador).get(project.url("edit")).content.decode()
    assert 'value="Lehmbau, ' in form_page
    _client(ambassador).post(project.url("edit"), {
        "kind": "project", "title": "Cob oven", "skills_to_learn": "Clay building", **_formset([]),
    })
    assert [s.skill.slug for s in project.skills_to_learn()] == ["clay-building"]
    assert skill_offers(community).count() == 1
    # Once the project is over, the community no longer lists them
    project.archived_at = timezone.now()
    project.save()
    assert not skill_offers(community).current().exists()


@pytest.mark.django_db
def test_event_list_finds_events_by_skill_to_learn(project, helper):
    skill_offer(project.community, Skill.objects.create(name="Welding", slug="welding"), event=project)
    assert _titles(_client(helper).get(_LIST, {"q": "weld"})) == ["Rocket stove"]
    assert _titles(_client(helper).get(_LIST, {"q": "pottery"})) == []


@pytest.mark.django_db
def test_communities_are_found_by_their_current_projects(community, project):
    other = Community.objects.create(name="Elsewhere", owner=User.objects.create_user(email="o@example.com", password="x"))
    list_url = reverse("communities:api-list")
    content = Client().get(list_url + "?q=rocket").content.decode()
    assert "Sonnenhof" in content and "Elsewhere" not in content
    suggestions = Client().get(reverse("communities:api-suggest") + "?q=rocket").json()
    assert {"value": "Rocket stove", "type": "event"} in suggestions
    # Not by an archived one
    project.archived_at = timezone.now()
    project.save()
    assert "Sonnenhof" not in Client().get(list_url + "?q=rocket").content.decode()


@pytest.mark.django_db
def test_community_cards_list_current_projects_with_dates(community, project):
    ongoing = Event.objects.create(community=community, title="Food forest care")
    Event.objects.create(community=community, title="Old barn", archived_at=timezone.now())
    content = Client().get(reverse("communities:api-list")).content.decode()
    assert project.get_absolute_url() in content and ongoing.get_absolute_url() in content
    assert "Old barn" not in content
    # Dated projects first, by start; ongoing ones after them
    assert content.index("Rocket stove") < content.index("Food forest care")
    assert project.starts_on.strftime("%-d %b") in content


@pytest.mark.django_db
def test_only_the_ambassador_creates_and_edits(community, project, helper):
    client = _client(helper)
    assert client.get(reverse("events:create", args=[community.slug])).status_code == 403
    assert client.get(project.url("edit")).status_code == 403
    assert client.post(project.url("archive")).status_code == 403


@pytest.mark.django_db
def test_end_before_start_is_rejected(community, ambassador):
    response = _client(ambassador).post(reverse("events:create", args=[community.slug]), {
        "kind": "project", "title": "Backwards", "starts_on": "2030-03-01", "ends_on": "2030-02-01", **_formset([]),
    })
    assert response.status_code == 200
    assert list(response.context["form"].errors) == ["ends_on"]
    assert not Event.objects.filter(title="Backwards").exists()


@pytest.mark.django_db
def test_editing_removes_needs_and_marks_the_project_fresh(project, ambassador):
    Event.objects.filter(pk=project.pk).update(updated_at=timezone.now() - timedelta(days=30))
    masonry, clay = project.needs()
    data = {
        "kind": "project", "title": "Rocket stove", "starts_on": project.starts_on.isoformat(), "ends_on": project.ends_on.isoformat(),
        "needs-TOTAL_FORMS": "2", "needs-INITIAL_FORMS": "2", "needs-MIN_NUM_FORMS": "0", "needs-MAX_NUM_FORMS": "1000",
        "needs-0-random_id": masonry.pk, "needs-0-kind": "hands", "needs-0-title": "Masonry", "needs-0-DELETE": "on",
        "needs-1-random_id": clay.pk, "needs-1-kind": "material", "needs-1-title": "Clay", "needs-1-quantity": "300", "needs-1-unit": "kg",
    }
    response = _client(ambassador).post(project.url("edit"), data)
    assert response.status_code == 302, (response.context["form"].errors, response.context["formset"].errors)
    project.refresh_from_db()
    assert [(n.title, n.amount) for n in project.needs()] == [("Clay", "300 kg")]
    assert timezone.now() - project.updated_at < timedelta(minutes=1)


# ── Listing ───────────────────────────────────────────────────────────


_LIST = reverse_lazy("events:api-list")
_MARKERS = reverse_lazy("events:api-markers")


def _titles(response):
    return [event.title for event in response.context["events"]]


@pytest.mark.django_db
def test_event_list_is_a_map_open_to_everyone_with_current_events_only(community, project, helper):
    assert Client().get(reverse("events:list")).status_code == 200
    today = timezone.localdate()
    Event.objects.create(community=community, title="Ongoing garden")
    Event.objects.create(community=community, title="Old roof", ends_on=today - timedelta(days=1))
    Event.objects.create(community=community, title="Shelved", archived_at=timezone.now())
    # Without a place in one's profile: all of them, everywhere
    assert set(_titles(_client(helper).get(_LIST))) == {"Rocket stove", "Ongoing garden"}
    assert set(_titles(Client().get(_LIST))) == {"Rocket stove", "Ongoing garden"}


@pytest.mark.django_db
def test_event_markers_are_where_everyone_sees_them_in_the_visible_area(community, project, ambassador):
    Community.objects.filter(pk=community.pk).update(location=Point(13.4, 52.5), location_public=True, location_name="Sonnendorf")
    far = Community.objects.create(name="Waldgarten", owner=ambassador, location=Point(2.35, 48.85), location_public=True)
    Event.objects.create(community=far, title="Forest garden days")
    features = Client().get(_MARKERS).json()["features"]
    assert {f["properties"]["title"] for f in features} == {"Rocket stove", "Forest garden days"}
    rocket = next(f for f in features if f["properties"]["title"] == "Rocket stove")
    assert rocket["geometry"]["coordinates"] == [13.4, 52.5]
    assert rocket["properties"]["needs"] == ["Masonry", "Clay"] and rocket["properties"]["colour"] == "#9b5506"
    # Its host with the avatar, as on the cards
    assert "Sonnenhof" in rocket["properties"]["host"] and community.get_absolute_url() in rocket["properties"]["host"]
    # Where it is, the map shows
    assert "Sonnendorf" not in rocket["properties"]["host"]
    # The dates as text, for the popup
    assert "<" not in rocket["properties"]["dates"] and " – " in rocket["properties"]["dates"]
    features = Client().get(_MARKERS, {"bbox": "10,50,15,55"}).json()["features"]
    assert [f["properties"]["title"] for f in features] == ["Rocket stove"]


@pytest.mark.django_db
def test_event_list_is_nearest_first(community, project, ambassador, helper):
    Community.objects.filter(pk=community.pk).update(location=Point(13.4, 52.5), location_public=True)
    far = Community.objects.create(name="Waldgarten", owner=ambassador, location=Point(2.35, 48.85), location_public=True)
    Event.objects.create(community=far, title="Forest garden days")
    # From the place in one's profile
    User.objects.filter(pk=helper.pk).update(location=Point(13.0, 52.4))
    response = _client(helper).get(_LIST)
    assert _titles(response) == ["Rocket stove", "Forest garden days"] and response.context["events"][0].km < 50
    # From where one is
    response = Client().get(_LIST, {"near": "48.9,2.3"})
    assert _titles(response) == ["Forest garden days", "Rocket stove"] and response.context["events"][0].km < 10
    # Not a place: as without it
    assert Client().get(_LIST, {"near": "here"}).context["events"][0].km is None


@pytest.mark.django_db
def test_event_list_filters_by_kinds(community, project):
    Event.objects.create(community=community, title="Open day", kind=Event.KIND_COMMUNITY_EVENT)
    assert _titles(Client().get(_LIST, {"kind": "community_event"})) == ["Open day"]
    assert len(_titles(Client().get(_LIST, {"kind": "community_event,project"}))) == 2


@pytest.mark.django_db
def test_going_to_lists_the_events_ones_coming_or_help_was_accepted(community, project, helper):
    today = timezone.localdate()
    open_day = Event.objects.create(community=community, title="Open day", starts_on=today + timedelta(days=2))
    asked = Event.objects.create(community=community, title="Harvest", starts_on=today + timedelta(days=1))
    over = Event.objects.create(community=community, title="Old roof", ends_on=today - timedelta(days=1))
    for event in (project, open_day, over):
        _offer(event, helper, status=Match.STATUS_ACCEPTED)
    _offer(asked, helper)
    # Not the ones still asked for or over, until one looks at the past
    assert set(_titles(_client(helper).get(_LIST, {"going": "1"}))) == {"Open day", "Rocket stove"}
    assert _titles(_client(helper).get(_LIST, {"going": "1", "when": "past"})) == ["Old roof"]
    # Only logged in
    assert len(_titles(Client().get(_LIST, {"going": "1"}))) == 3


@pytest.mark.django_db
def test_event_list_shows_upcoming_or_past_events(community, project):
    today = timezone.localdate()
    Event.objects.create(community=community, title="Running now", starts_on=today - timedelta(days=1))
    Event.objects.create(community=community, title="Last summer", starts_on=today - timedelta(days=90), ends_on=today - timedelta(days=60))
    Event.objects.create(community=community, title="Long ago", ends_on=today - timedelta(days=400), archived_at=timezone.now())
    assert set(_titles(Client().get(_LIST))) == {"Rocket stove", "Running now"}
    assert _titles(Client().get(_LIST, {"when": "upcoming"})) == ["Rocket stove"]
    # The latest first, archived ones too once they are over
    assert _titles(Client().get(_LIST, {"when": "past"})) == ["Last summer", "Long ago"]


@pytest.mark.django_db
def test_event_list_filters_by_country_dates_and_what_is_provided(community, project, ambassador):
    today = timezone.localdate()
    Community.objects.filter(pk=community.pk).update(country="DE")
    elsewhere = Community.objects.create(name="Finca", owner=ambassador, country="ES")
    Event.objects.create(community=elsewhere, title="Olive harvest", is_open=True, bed_provided=True,
                         starts_on=today + timedelta(days=60), ends_on=today + timedelta(days=70))
    assert _titles(Client().get(_LIST, {"country": "ES"})) == ["Olive harvest"]
    assert [code for code, _name in Client().get(reverse("events:list")).context["countries"]] == ["DE", "ES"]
    assert _titles(Client().get(_LIST, {"until": (today + timedelta(days=10)).isoformat()})) == ["Rocket stove"]
    assert _titles(Client().get(_LIST, {"from": (today + timedelta(days=50)).isoformat()})) == ["Olive harvest"]
    assert _titles(Client().get(_LIST, {"open": "1"})) == ["Olive harvest"]
    assert _titles(Client().get(_LIST, {"bed": "1"})) == ["Olive harvest"]
    assert _titles(Client().get(_LIST, {"food": "1", "open": "1"})) == []


@pytest.mark.django_db
def test_event_list_filters_by_skills_to_learn_and_fitting_ones_skills(community, project, helper):
    welding = Skill.objects.create(name="Welding", slug="welding")
    masonry = Skill.objects.create(name="Masonry", slug="masonry")
    other = Event.objects.create(community=community, title="Open workshop")
    skill_offer(community, welding, event=other)
    assert _titles(Client().get(_LIST, {"learn": "Welding,"})) == ["Open workshop"]
    # A need for a skill one offers, or a skill one wishes to learn
    need(project, kind=Listing.KIND_HANDS, title="Walls", skill=masonry)
    skill_offer(helper, masonry)
    assert _titles(_client(helper).get(_LIST, {"fits": "1"})) == ["Rocket stove"]
    skill_wish(helper, welding)
    assert set(_titles(_client(helper).get(_LIST, {"fits": "1"}))) == {"Rocket stove", "Open workshop"}
    # Only logged in
    assert len(_titles(Client().get(_LIST, {"fits": "1"}))) == 2


@pytest.mark.django_db
def test_event_list_filters_by_what_is_still_needed(community, project):
    Event.objects.create(community=community, title="Open day")
    assert _titles(Client().get(_LIST, {"needs": "material"})) == ["Rocket stove"]
    assert _titles(Client().get(_LIST, {"needs": "tool"})) == []
    assert _titles(Client().get(_LIST, {"needs": "tool,hands"})) == ["Rocket stove"]


@pytest.mark.django_db
def test_event_list_filters_by_room_left(community, project, helper, ambassador):
    today = timezone.localdate()
    full = Event.objects.create(community=community, title="Small course", volunteers_wanted=1,
                                starts_on=today + timedelta(days=1), ends_on=today + timedelta(days=2))
    match = _offer(full, helper, status=Match.STATUS_ACCEPTED, stay=(_aware(today + timedelta(days=1)), _aware(today + timedelta(days=2))))
    assert _titles(Client().get(_LIST, {"room": "1"})) == ["Rocket stove"]
    # A day free again: room
    StayDetails.objects.filter(match=match).update(stay_to=_aware(today + timedelta(days=1)))
    assert set(_titles(Client().get(_LIST, {"room": "1"}))) == {"Rocket stove", "Small course"}
    # Nobody to answer: none
    Community.objects.filter(pk=community.pk).update(owner=None)
    assert _titles(Client().get(_LIST, {"room": "1"})) == []


@pytest.mark.django_db
def test_event_search_suggests_events_hosts_skills_and_places(community, project):
    Community.objects.filter(pk=community.pk).update(location_name="Sonnendorf")
    skill_offer(community, Skill.objects.create(name="Sowing", slug="sowing"), event=project)
    found = Client().get(reverse("events:api-suggest"), {"q": "so"}).json()
    assert {"value": "Sonnenhof", "type": "community"} in found
    assert {"value": "Sowing", "type": "skill"} in found
    assert {"value": "Sonnendorf", "type": "location"} in found
    assert Client().get(reverse("events:api-suggest"), {"q": "rocket"}).json() == [{"value": "Rocket stove", "type": "event"}]
    assert Client().get(reverse("events:api-suggest"), {"q": "rocket", "when": "past"}).json() == []


@pytest.mark.django_db
def test_events_have_a_main_menu_entry_and_going_to_in_ones_menu(project, helper):
    content = Client().get(project.get_absolute_url()).content.decode()
    going = f'href="{reverse("events:going")}"'
    assert f'href="{reverse("events:list")}"' in content and going not in content
    assert going in _client(helper).get(project.get_absolute_url()).content.decode()


@pytest.mark.django_db
def test_going_to_page_lists_upcoming_soonest_first_and_past_latest_first(community, project, helper):
    today = timezone.localdate()
    running = Event.objects.create(community=community, title="Running now", starts_on=today - timedelta(days=3))
    soon = Event.objects.create(community=community, title="Open day", starts_on=today + timedelta(days=1), ends_on=today + timedelta(days=1))
    last_year = Event.objects.create(community=community, title="Last year", ends_on=today - timedelta(days=300))
    last_month = Event.objects.create(community=community, title="Last month", ends_on=today - timedelta(days=30), archived_at=timezone.now())
    Event.objects.create(community=community, title="Not mine", starts_on=today + timedelta(days=2))
    for event in (project, running, soon, last_year, last_month):
        _offer(event, helper, status=Match.STATUS_ACCEPTED)

    def titles(**params):
        return [event.title for event in _client(helper).get(reverse("events:going"), params).context["page"]]

    assert titles() == ["Running now", "Open day", "Rocket stove"]
    assert titles(when="past") == ["Last month", "Last year"]
    content = _client(helper).get(reverse("events:going")).content.decode()
    assert f'{reverse("events:list")}?going=1&amp;view=list' in content
    # Only logged in
    assert Client().get(reverse("events:going")).status_code == 302


@pytest.mark.django_db
def test_community_page_shows_its_projects(community, project, ambassador):
    content = Client().get(community.get_absolute_url()).content.decode()
    assert "Rocket stove" in content
    assert reverse("events:create", args=[community.slug]) not in content
    content = _client(ambassador).get(community.get_absolute_url()).content.decode()
    assert reverse("events:create", args=[community.slug]) in content


# ── Offering help ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_offering_help_creates_a_stay_match_with_the_needs(project, helper, ambassador):
    masonry, clay = project.needs()
    response = _client(helper).post(project.url("offer_help"), {
        f"need_{masonry.pk}": "on", f"need_{clay.pk}": "on", f"quantity_{clay.pk}": "50",
        "stay_from": project.starts_on.isoformat(), "stay_to": (project.starts_on + timedelta(days=6)).isoformat(),
        "message": "I can build and bring clay.",
    })
    match = Match.objects.get()
    assert response.status_code == 302 and response.url == match.get_absolute_url()
    assert match.target == project and match.recipient == ambassador and match.from_user == helper
    assert match.is_community_stay
    assert {c.listing for c in match.brings()} == {masonry, clay}
    assert {(c.listing, c.quantity) for c in match.contributions.all()} == {(masonry, None), (clay, 50)}
    assert match.stay_period() == (_aware(project.starts_on), _aware(project.starts_on + timedelta(days=6)))
    notification = Notification.objects.get(recipient=ambassador)
    assert notification.icon == "fa-person-digging"
    with translation.override("en"):
        assert notification.text == "Hugo offered to help with your project: Rocket stove"
    assert len(mail.outbox) == 1 and "Clay (50 kg)" in mail.outbox[0].body
    masonry.refresh_from_db()
    assert masonry.status == Listing.STATUS_OFFERED


@pytest.mark.django_db
def test_no_offers_on_ended_projects_or_from_the_ambassador(project, helper, ambassador):
    assert _client(ambassador).get(project.url("offer_help")).status_code == 302
    Event.objects.filter(pk=project.pk).update(archived_at=timezone.now())
    _client(helper).post(project.url("offer_help"), {"message": "Hi"})
    assert not Match.objects.exists()


@pytest.mark.django_db
def test_need_status_follows_offers_and_the_ambassador(project, helper, ambassador):
    masonry = project.listings.filter(type="wish").get(title="Masonry")
    assert masonry.status == Listing.STATUS_OPEN
    match = _offer(project, helper, needs=[masonry])
    assert Listing.objects.get(pk=masonry.pk).status == Listing.STATUS_OFFERED
    Match.objects.filter(pk=match.pk).update(status=Match.STATUS_ACCEPTED)
    masonry = Listing.objects.get(pk=masonry.pk)
    assert masonry.status == Listing.STATUS_PROMISED and masonry.promised_by() == [helper]

    url = project.url("toggle_need", masonry.pk)
    _client(ambassador).post(url)
    assert Listing.objects.get(pk=masonry.pk).status == Listing.STATUS_COVERED
    _client(ambassador).post(url)
    assert Listing.objects.get(pk=masonry.pk).covered_at is None


@pytest.mark.django_db
def test_project_offers_are_volunteer_visits(project, helper, ambassador):
    _offer(project, helper)
    content = _client(ambassador).get(reverse("matches:list"), {"type": "volunteer"}).content.decode()
    assert "Rocket stove" in content


@pytest.mark.django_db
def test_counter_proposed_dates_are_the_stay_period(project, helper, ambassador):
    day = project.starts_on
    match = _offer(project, helper, stay=(_aware(day), _aware(day + timedelta(days=3))))
    MatchMessage.objects.create(
        match=match, sender=ambassador, status_to=Match.STATUS_COUNTER,
        counter_stay_from=_aware(day + timedelta(days=10)), counter_stay_to=_aware(day + timedelta(days=12)),
    )
    assert match.stay_period() == (_aware(day + timedelta(days=10)), _aware(day + timedelta(days=12)))


@pytest.mark.django_db
def test_helper_writes_a_reference_about_the_community(project, helper, ambassador):
    match = _offer(project, helper, status=Match.STATUS_ACCEPTED)
    assert match_reference_subject(match, helper) == (project.community, "", "")
    assert match_reference_subject(match, ambassador) == (helper, "", "")
    with translation.override("en"):
        assert exchange_text(match, helper) == "Your help with Rocket stove at Sonnenhof"
        assert exchange_text(match, ambassador) == "Hugo's help with Rocket stove"


# ── Calendar ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_calendar_is_for_the_ambassador_only(community, helper):
    assert _client(helper).get(reverse("matches:calendar", args=[community.slug])).status_code == 403


@pytest.mark.django_db
def test_calendar_shows_stays_and_warns_about_overbooking(community, project, ambassador):
    day = project.starts_on
    guests = [User.objects.create_user(email=f"g{i}@example.com", password="x", name=f"Guest {i}") for i in range(4)]
    _offer(project, guests[0], Match.STATUS_ACCEPTED, stay=(_aware(day), _aware(day + timedelta(days=2))))
    _offer(project, guests[1], Match.STATUS_ACCEPTED, stay=(_aware(day), _aware(day + timedelta(days=2))))
    _offer(project, guests[2], Match.STATUS_ACCEPTED, stay=(_aware(day + timedelta(days=1)), None))
    _offer(project, guests[3], Match.STATUS_PENDING)  # no dates
    # A plain volunteer stay at the community counts too; a declined one doesn't
    stay = Match(from_user=guests[3], recipient=ambassador, message="Hi", status=Match.STATUS_DECLINED)
    stay.target = community
    stay.save()

    dated, undated = stays_of(community)
    assert len(dated) == 3 and len(undated) == 1

    response = _client(ambassador).get(
        reverse("matches:calendar", args=[community.slug]), {"month": (day + timedelta(days=1)).strftime("%Y-%m")},
    )
    assert response.status_code == 200
    overbooked = [d.date for d in response.context["overbooked_days"]]
    assert overbooked == [day + timedelta(days=1)]  # three confirmed, room for two
    content = response.content.decode()
    assert "Guest 0" in content and "Guest 3" in content


@pytest.mark.django_db
def test_calendar_lists_open_needs(community, project, ambassador):
    project.listings.filter(type="wish").filter(title="Clay").update(covered_at=timezone.now())
    response = _client(ambassador).get(
        reverse("matches:calendar", args=[community.slug]), {"month": project.starts_on.strftime("%Y-%m")},
    )
    [(listed, needs)] = response.context["open_needs"]
    assert listed == project and [n.title for n in needs] == ["Masonry"]


@pytest.mark.django_db
def test_calendar_lists_needs_of_all_coming_projects_whatever_the_month(community, project, ambassador):
    today = timezone.localdate()
    later = Event.objects.create(community=community, title="Greenhouse", starts_on=today + timedelta(days=200))
    need(later, kind=Listing.KIND_MATERIAL, title="Glass")
    over = Event.objects.create(community=community, title="Old roof", ends_on=today - timedelta(days=1))
    need(over, kind=Listing.KIND_MATERIAL, title="Tiles")
    response = _client(ambassador).get(reverse("matches:calendar", args=[community.slug]), {"month": "2000-01"})
    assert [p.title for p, _ in response.context["open_needs"]] == ["Rocket stove", "Greenhouse"]


@pytest.mark.django_db
def test_covered_needs_are_celebrated_with_their_helpers(community, project, ambassador, helper):
    masonry, clay = project.needs()
    offer = _offer(project, helper, Match.STATUS_ACCEPTED, needs=[masonry])
    clay.covered_at = timezone.now()
    clay.save()
    response = _client(ambassador).get(reverse("matches:calendar", args=[community.slug]))
    assert response.context["covered_count"] == 2

    url = reverse("matches:calendar_covered", args=[community.slug])
    response = _client(ambassador).get(url)
    [(listed, needs)] = response.context["covered_needs"]
    assert listed == project
    assert [(n.title, [h.person for h in people]) for n, people in needs] == [("Masonry", [helper]), ("Clay", [])]
    assert response.context["helper_count"] == 1
    content = response.content.decode()
    assert "Hugo" in content and offer.get_absolute_url() in content
    # The ambassador is asked for a reference until they have written one
    assert f"{helper.get_absolute_url()}#references" in content

    from gift_economy.references.models import Reference
    Reference.objects.create(author=ambassador, recipient=helper, subject=helper, match=offer, text="Strong hands")
    assert f"{helper.get_absolute_url()}#references" not in _client(ambassador).get(url).content.decode()


@pytest.mark.django_db
def test_covered_needs_are_for_the_ambassador_only(community, helper):
    assert _client(helper).get(reverse("matches:calendar_covered", args=[community.slug])).status_code == 403


@pytest.mark.django_db
def test_calendar_survives_a_bad_month(community, ambassador):
    response = _client(ambassador).get(reverse("matches:calendar", args=[community.slug]), {"month": "nope"})
    assert response.status_code == 200


# ── Freshness ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_ended_projects_are_archived_without_looking_updated(community):
    ended = Event.objects.create(community=community, title="Done", ends_on=timezone.localdate() - timedelta(days=1))
    updated_at = ended.updated_at
    assert archive_stale_events() == (1, 0)
    ended.refresh_from_db()
    assert ended.archived_at is not None and ended.updated_at == updated_at


@pytest.mark.django_db
def test_stale_projects_are_asked_about_then_archived(community):
    stale = Event.objects.create(community=community, title="Garden")
    Event.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=61))

    assert archive_stale_events() == (0, 1)
    assert mail.outbox[0].to == ["amb@example.com"]
    assert "Garden" in mail.outbox[0].subject and "noch aktuell" in mail.outbox[0].subject  # her language
    assert make_confirm_token(stale)[:10] in mail.outbox[0].body
    # Asked only once
    assert archive_stale_events() == (0, 0)

    later = timezone.now() + timedelta(days=15)
    assert archive_stale_events(now=later) == (1, 0)
    assert Event.objects.get(pk=stale.pk).archived_at is not None


@pytest.mark.django_db
def test_events_with_their_days_ahead_are_left_alone(community):
    today = timezone.localdate()
    Event.objects.create(community=community, title="Harvest", starts_on=today + timedelta(days=90), ends_on=today + timedelta(days=92))
    Event.objects.create(community=community, title="From spring on", starts_on=today + timedelta(days=30))
    # Ongoing, but only since last week
    Event.objects.create(community=community, title="Just started", starts_on=today - timedelta(days=7))
    Event.objects.update(updated_at=timezone.now() - timedelta(days=200))
    assert archive_stale_events() == (0, 0)


@pytest.mark.django_db
def test_one_click_confirms_and_brings_back(community):
    stale = Event.objects.create(
        community=community, title="Garden", archived_at=timezone.now(), stale_reminder_sent_at=timezone.now(),
    )
    Event.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=80))
    response = Client().get(stale.url("confirm_by_email", make_confirm_token(stale)))
    assert response.status_code == 302
    stale.refresh_from_db()
    assert stale.archived_at is None and stale.stale_reminder_sent_at is None
    assert timezone.now() - stale.updated_at < timedelta(minutes=1)
    assert Client().get(stale.url("confirm_by_email", "forged")).status_code == 400


@pytest.mark.django_db
def test_an_ended_project_is_not_brought_back_by_confirming(community, ambassador):
    ended = Event.objects.create(
        community=community, title="Done", ends_on=date(2020, 1, 1), archived_at=timezone.now(),
    )
    _client(ambassador).post(ended.url("confirm"))
    assert Event.objects.get(pk=ended.pk).archived_at is not None


@pytest.mark.django_db
def test_last_seen_is_kept_up_to_date(helper):
    assert helper.last_active is None
    _client(helper).get(reverse("events:list"))
    helper.refresh_from_db()
    assert helper.last_seen is not None and helper.last_active == helper.last_seen


def test_ago_reads_in_days():
    now = timezone.now()
    with translation.override("en"):
        assert ago(now) == "today"
        assert ago(now - timedelta(days=1)) == "yesterday"
        assert ago(now - timedelta(days=3)) == "3\xa0days ago"
    with translation.override("es"):
        assert ago(now - timedelta(days=3)) == "hace 3\xa0días"
    assert ago(None) == ""


@pytest.mark.django_db
def test_staff_read_matches_but_cannot_act(project, helper):
    staff = User.objects.create_user(email="staff@example.com", password="x", is_staff=True)
    stranger = User.objects.create_user(email="stranger@example.com", password="x")
    match = _offer(project, helper)
    url = reverse("matches:detail", args=[match.pk])
    assert _client(stranger).get(url).status_code == 404
    response = _client(staff).get(url)
    assert response.status_code == 200 and not response.context["is_party"]
    assert _client(staff).post(url, {"action": "accept"}).status_code == 403
    assert Match.objects.get(pk=match.pk).status == Match.STATUS_PENDING


@pytest.mark.django_db
def test_offers_cover_a_quantity_in_parts(project, helper, ambassador):
    clay = project.listings.filter(type="wish").get(title="Clay")  # 200 kg
    first = _offer(project, helper, Match.STATUS_ACCEPTED)
    Contribution.objects.create(listing=clay, match=first, quantity=120)
    clay = Listing.objects.get(pk=clay.pk)
    assert clay.status == Listing.STATUS_OFFERED and clay.remaining == 80
    with translation.override("en"):
        assert clay.progress == "120 of 200 kg promised"

    other = User.objects.create_user(email="other@example.com", password="x", name="Olu")
    second = _offer(project, other, Match.STATUS_PENDING)
    Contribution.objects.create(listing=clay, match=second, quantity=80)
    assert Listing.objects.get(pk=clay.pk).offered_quantity == 80
    Match.objects.filter(pk=second.pk).update(status=Match.STATUS_ACCEPTED)
    clay = Listing.objects.get(pk=clay.pk)
    assert clay.status == Listing.STATUS_PROMISED and clay.remaining == 0 and clay.progress == ""


@pytest.mark.django_db
def test_offer_form_only_lists_needs_still_missing(project, helper):
    masonry = project.listings.filter(type="wish").get(title="Masonry")
    match = _offer(project, helper, Match.STATUS_ACCEPTED)
    Contribution.objects.create(listing=masonry, match=match)
    other = User.objects.create_user(email="other@example.com", password="x")
    response = _client(other).get(project.url("offer_help"))
    assert [need.title for need, _box, _amount in response.context["form"].need_rows()] == ["Clay"]


# ── On the gifts map and list ─────────────────────────────────────────


@pytest.fixture
def mapped(community, project):
    from django.contrib.gis.geos import Point
    community.location = Point(14.98, 51.16, srid=4326)
    community.save()
    return project


@pytest.mark.django_db
def test_open_needs_show_on_the_gifts_map(mapped):
    """Each open need of a current project is a marker at the community, a wish of it."""
    project = mapped
    project.listings.filter(type="wish").filter(title="Masonry").update(covered_at=timezone.now())

    def needs(params=None):
        features = Client().get(reverse("gifts:api-markers"), params or {}).json()["features"]
        return [f["properties"] for f in features if f["properties"]["event"]]

    [clay] = needs()  # covered ones drop off
    assert (clay["title"], clay["amount"], clay["event"], clay["community_name"]) == ("Clay", "200 kg", "Rocket stove", "Sonnenhof")
    assert clay["url"] == project.listings.get(title="Clay").get_absolute_url()

    # With the "need" or "wish" type or no type filter; outside the viewport not at all
    assert needs({"type": "need"}) and needs({"type": "wish"}) and not needs({"type": "offer"})
    assert not needs({"bbox": "0,0,1,1"})
    # The map zoomed out to the whole world
    assert needs({"bbox": "-180,-68.3239,180,79.2752"}) and needs({"bbox": "-100,-60,100,80"})
    # Not once the project is over
    project.archived_at = timezone.now()
    project.save()
    assert not needs()


@pytest.mark.django_db
def test_gifts_filters_apply_to_needs(mapped):
    project = mapped
    building = ListingCategory.objects.get(slug="building-renovation")
    garden = ListingCategory.objects.get(slug="garden-farm")
    project.listings.get(title="Clay").categories.add(building)

    def needs_of(params):
        features = Client().get(reverse("gifts:api-markers"), params).json()["features"]
        return sorted(f["properties"]["title"] for f in features if f["properties"]["event"])

    assert needs_of({"categories": building.pk}) == ["Clay"]
    assert needs_of({"categories": garden.pk}) == []
    assert needs_of({"search": "clay"}) == ["Clay"]
    assert needs_of({"search": "rocket"}) == ["Clay", "Masonry"]  # the project itself matches
    assert needs_of({"type": "need", "search": "nothing like it"}) == []
    # Clay is a material, Masonry helping hands (a skill)
    assert needs_of({"kind": "material"}) == ["Clay"]
    assert needs_of({"kind": "tool"}) == []
    assert needs_of({"type": "skill"}) == ["Masonry"]


@pytest.mark.django_db
def test_gifts_kind_filter(mapped, ambassador):
    from django.contrib.gis.geos import Point
    place = Point(14.98, 51.16, srid=4326)
    Listing.objects.create(title="Spade", type="offer", kind=Listing.KIND_TOOL, owner=ambassador, location=place)
    Listing.objects.create(title="Bricks", type="offer", kind=Listing.KIND_MATERIAL, owner=ambassador, location=place)
    ambassador.location = place
    ambassador.save()
    skill_offer(ambassador, Skill.objects.get_or_create(name="Masonry")[0])

    def sources(params):
        features = Client().get(reverse("gifts:api-markers"), params).json()["features"]
        return sorted(f["properties"].get("title") or f["properties"]["source"] for f in features)

    assert sources({"kind": "tool"}) == ["Spade"]  # no skills, no material
    assert sources({"kind": "material"}) == ["Bricks", "Clay"]  # Clay: the project's need
    # Markers show the kind, else a gift or a heart
    glyphs = {f["properties"]["title"]: f["properties"].get("glyph") for f in
              Client().get(reverse("gifts:api-markers")).json()["features"] if f["properties"]["listing_type"] == "offer"}
    assert glyphs == {"Spade": 0xF7D9, "Bricks": 0xF1B3, "Masonry": 0xF19D}
    assert Listing(type="wish").marker_glyph == 0xF004 and Listing(type="offer").marker_glyph == 0xF06B


@pytest.mark.django_db
def test_project_needs_in_the_gifts_list(mapped):
    content = Client().get(reverse("gifts:api-list"), {"type": "need"}).content.decode()
    assert "Rocket stove" in content and "Clay" in content
    # Listing types alone leave them out
    assert "Rocket stove" not in Client().get(reverse("gifts:api-list"), {"type": "offer"}).content.decode()


@pytest.mark.django_db
def test_project_page_links_the_people_who_promised(project, helper):
    clay = project.listings.filter(type="wish").get(title="Clay")  # 200 kg
    match = _offer(project, helper, Match.STATUS_ACCEPTED)
    Contribution.objects.create(listing=clay, match=match, quantity=120)
    with translation.override("en"):
        content = Client(HTTP_ACCEPT_LANGUAGE="en").get(project.get_absolute_url()).content.decode()
    assert "120 of 200 kg promised" in content
    assert f'<a href="{helper.get_absolute_url()}" class="underline hover:text-primary">Hugo</a> (120 kg)' in content


@pytest.mark.django_db
def test_project_page_shows_references_from_anything_part_of_it(community, project, ambassador, helper):
    """References after help offered on the project, or after a stay at its community that
    brought one of its needs; not other references about the community."""
    from gift_economy.references.models import Reference

    offer = _offer(project, helper, Match.STATUS_ACCEPTED)
    Reference.objects.create(author=helper, recipient=ambassador, subject=community, match=offer, text="Great build days")
    Reference.objects.create(author=ambassador, recipient=helper, subject=helper, match=offer, text="Strong hands")

    visitor = User.objects.create_user(email="v@example.com", password="x", name="Vera")
    stay = Match(from_user=visitor, recipient=ambassador, status=Match.STATUS_ACCEPTED)
    stay.target = community
    stay.save()
    Contribution.objects.create(listing=project.listings.filter(type="wish").get(title="Clay"), match=stay)
    Reference.objects.create(author=visitor, recipient=ambassador, subject=community, match=stay, text="Brought the clay")
    other = User.objects.create_user(email="o@example.com", password="x")
    Reference.objects.create(author=other, recipient=ambassador, subject=community, text="Unrelated visit")

    response = Client().get(project.get_absolute_url())
    assert sorted(r.text for r in response.context["references"]) == ["Brought the clay", "Great build days", "Strong hands"]
    content = response.content.decode()
    assert "References from this project" in content and "Unrelated visit" not in content


# ── Events: kinds, addresses, hours, just coming ──────────────────────


@pytest.fixture
def open_day(community):
    day = timezone.localdate() + timedelta(days=10)
    return Event.objects.create(
        community=community, kind=Event.KIND_COMMUNITY_EVENT, title="Open day", is_open=True,
        starts_on=day, ends_on=day, starts_at=time(14, 0), ends_at=time(18, 0),
    )


@pytest.mark.django_db
def test_an_event_lives_under_its_community_with_a_slug_of_its_own(community, ambassador, project):
    assert project.get_absolute_url() == f"/communities/{community.slug}/events/rocket-stove/"
    # The same title again, and titles that would be a path beside an event's page
    again = Event.objects.create(community=community, title="Rocket stove")
    new = Event.objects.create(community=community, title="New")
    assert (again.slug, new.slug) == ("rocket-stove-2", "new-2")
    # Another community can use the same slug; the address stays when the title changes
    other = Community.objects.create(name="Waldgarten", owner=ambassador)
    assert Event.objects.create(community=other, title="Rocket stove").slug == "rocket-stove"
    project.title = "Rocket mass heater"
    project.save()
    assert project.slug == "rocket-stove"
    assert Client().get(project.get_absolute_url()).status_code == 200
    assert Client().get(f"/communities/{other.slug}/events/rocket-stove-2/").status_code == 404


@pytest.mark.django_db
def test_a_kind_sets_what_a_new_event_starts_with(community, ambassador):
    client = _client(ambassador)
    create_url = reverse("events:create", args=[community.slug])
    assert client.get(create_url).context["form"].initial["is_open"] is False
    form = client.get(create_url, {"kind": "community_event"}).context["form"]
    assert form.initial["is_open"] is True and form.instance.kind == Event.KIND_COMMUNITY_EVENT
    # Every setting can be changed: a community event people ask first for
    client.post(create_url, {"kind": "community_event", "title": "Seminar", **_formset([])})
    seminar = Event.objects.get(title="Seminar")
    assert seminar.kind == Event.KIND_COMMUNITY_EVENT and not seminar.is_open
    with translation.override("en"):
        assert str(seminar.kind_label) == "Community event"
        assert seminar.get_match_kind() == ("Community event", "fa-people-group", "bg-green")


@pytest.mark.django_db
def test_an_open_day_with_hours(community, ambassador):
    response = _client(ambassador).post(reverse("events:create", args=[community.slug]), {
        "kind": "community_event", "title": "Open day", "is_open": "on",
        "starts_on": "2030-06-01", "ends_on": "2030-06-01", "starts_at": "14:00", "ends_at": "18:00",
        **_formset([]),
    })
    assert response.status_code == 302
    event = Event.objects.get(title="Open day")
    assert (event.starts_at, event.ends_at, event.is_open, event.is_one_day) == (time(14, 0), time(18, 0), True, True)
    with translation.override("en"):
        content = Client().get(event.get_absolute_url()).content.decode()
    assert "14:00–18:00" in content and "Community event" in content
    # No needs and nothing provided: those sections are left out
    assert "What is needed" not in content and "What the community provides" not in content

    # Hours the wrong way round on one day
    response = _client(ambassador).post(reverse("events:create", args=[community.slug]), {
        "kind": "community_event", "title": "Backwards", "starts_on": "2030-06-01", "ends_on": "2030-06-01",
        "starts_at": "18:00", "ends_at": "14:00", **_formset([]),
    })
    assert response.status_code == 200 and not Event.objects.filter(title="Backwards").exists()


@pytest.mark.django_db
def test_just_coming_needs_no_answer_and_shows_in_the_calendar(community, open_day, helper, ambassador):
    mail.outbox.clear()
    with translation.override("en"):
        content = _client(helper).get(open_day.get_absolute_url()).content.decode()
    assert "I&#x27;m coming" in content or "I'm coming" in content
    response = _client(helper).post(open_day.url("come"), {"people": "3"})
    assert response.status_code == 302
    match = Match.objects.get(from_user=helper)
    assert match.target == open_day and match.recipient == ambassador
    assert match.status == Match.STATUS_ACCEPTED and match.is_coming and match.people == 3
    assert timezone.localdate(match.stay_details.stay_from) == open_day.starts_on
    # Nobody has to answer, and the host gets no message per person
    assert mail.outbox == [] and not Notification.objects.filter(recipient=ambassador).exists()

    # Pressing it twice doesn't count twice
    _client(helper).post(open_day.url("come"), {"people": "3"})
    assert Match.objects.filter(from_user=helper).count() == 1

    # The page lists who comes; the calendar counts the people on that day
    User.objects.filter(pk=ambassador.pk).update(language="en")  # their saved language is German
    content = _client(ambassador).get(open_day.get_absolute_url()).content.decode()
    assert "Who is coming" in content and "Hugo" in content and "3 people so far" in content
    response = _client(ambassador).get(
        reverse("matches:calendar", args=[community.slug]), {"month": open_day.starts_on.strftime("%Y-%m")},
    )
    day = next(d for week in response.context["weeks"] for d in week if d.date == open_day.starts_on)
    assert day.confirmed == 3 and day.events == [open_day]
    # Three people where there is room for two
    assert [d.date for d in response.context["overbooked_days"]] == [open_day.starts_on]
    assert "14:00" in response.content.decode()


@pytest.mark.django_db
def test_coming_can_be_taken_back(open_day, helper):
    client = _client(helper)
    client.post(open_day.url("come"), {"people": "2"})
    with translation.override("en"):
        assert "You are coming, 2 people." in client.get(open_day.get_absolute_url()).content.decode()
    client.post(open_day.url("not_coming"))
    assert not Match.objects.filter(from_user=helper).exists()


@pytest.mark.django_db
def test_just_coming_only_where_people_just_come(project, open_day, helper, ambassador):
    # Where people ask first there is nothing to press
    _client(helper).post(project.url("come"), {"people": "1"})
    assert not Match.objects.exists()
    # Not to one's own event, not to one that is over, and not without saying how many
    _client(ambassador).post(open_day.url("come"), {"people": "1"})
    _client(helper).post(open_day.url("come"), {"people": "0"})
    assert not Match.objects.exists()
    Event.objects.filter(pk=open_day.pk).update(archived_at=timezone.now())
    _client(helper).post(open_day.url("come"), {"people": "1"})
    assert not Match.objects.exists()
    assert Client().post(open_day.url("come"), {"people": "1"}).status_code == 302  # to the login


@pytest.mark.django_db
def test_who_is_coming_names_people_to_logged_in_visitors_only(open_day, helper):
    _client(helper).post(open_day.url("come"), {"people": "2"})
    with translation.override("en"):
        content = Client().get(open_day.get_absolute_url()).content.decode()
    assert "2 people so far" in content and "Hugo" not in content


@pytest.mark.django_db
def test_a_visit_to_an_open_event_is_what_references_are_about(open_day, helper, ambassador):
    _client(helper).post(open_day.url("come"), {"people": "1"})
    match = Match.objects.get(from_user=helper)
    assert match_reference_subject(match, helper)[0] == open_day.community
    with translation.override("en"):
        assert str(exchange_text(match, helper)) == "Your visit to Open day at Sonnenhof"
        assert str(match.kind[0]) == "Community event"


@pytest.mark.django_db
def test_texts_say_the_kinds_word(community, open_day, project):
    Event.objects.filter(pk=open_day.pk).update(starts_on=None, ends_on=None, updated_at=timezone.now() - timedelta(days=61))
    mail.outbox.clear()
    assert archive_stale_events() == (0, 1)
    assert "Gemeinschafts-Event" in mail.outbox[0].subject or "community event" in mail.outbox[0].subject
    with translation.override("en"):
        assert str(open_day.texts["ended"]) == "This community event is over."
        assert str(project.texts["ended"]) == "This project has ended."


@pytest.mark.django_db
def test_who_withdrew_can_ask_again(project, helper):
    match = _offer(project, helper, Match.STATUS_WITHDRAWN)
    content = _client(helper).get(project.get_absolute_url()).content.decode()
    assert "You already offered help." not in content
    assert match not in _client(project.manager).get(project.get_absolute_url()).context["offers"]


@pytest.mark.django_db
def test_who_withdrew_can_come_again(open_day, helper):
    _client(helper).post(open_day.url("come"), {"people": "1"})
    Match.objects.filter(from_user=helper).update(status=Match.STATUS_WITHDRAWN)
    _client(helper).post(open_day.url("come"), {"people": "2"})
    assert Match.objects.get(from_user=helper, status=Match.STATUS_ACCEPTED).people == 2
