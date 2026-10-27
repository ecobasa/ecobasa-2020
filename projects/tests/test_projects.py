from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone, translation

from communities.models import Community
from gifts.models import ListingCategory
from matches.models import Match, MatchMessage, VolunteerDetails
from notifications.models import Notification
from references.models import match_reference_subject
from references.reference_requests import exchange_text
from skills.models import SkillTaxonomy
from templatetags.site_tags import ago
from users.models import User

from matches.calendar import stays_of
from ..freshness import archive_stale_projects, make_confirm_token
from ..models import Need, NeedOffer, Project


@pytest.fixture(autouse=True)
def site(settings):
    settings.SITE_URL = "https://ecobasa.test"
    settings.PROJECT_STALE_DAYS = 60
    settings.PROJECT_ARCHIVE_GRACE_DAYS = 14


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
    project = Project.objects.create(
        community=community, title="Rocket stove",
        starts_on=today + timedelta(days=5), ends_on=today + timedelta(days=40), food_provided=True,
    )
    Need.objects.create(project=project, kind=Need.KIND_SKILL, title="Masonry", order=0)
    Need.objects.create(project=project, kind=Need.KIND_MATERIAL, title="Clay", quantity=200, unit="kg", order=1)
    return project


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _offer(project, user, status=Match.STATUS_PENDING, needs=(), stay=(None, None)):
    match = Match(from_user=user, recipient=project.community.owner, message="Hi", status=status)
    match.target = project
    match.save()
    VolunteerDetails.objects.create(match=match, stay_from=stay[0], stay_to=stay[1])
    match.needs.set(needs)
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
    category = ListingCategory.objects.create(name="Building Materials")
    response = _client(ambassador).post(reverse("projects:create", args=[community.slug]), {
        "title": "Guest house", "starts_on": "2030-03-01", "ends_on": "2030-04-30", "food_provided": "on",
        **_formset([
            {"kind": "skill", "title": "Zimmerei", "quantity": "2"},
            {"kind": "skill", "title": "Helping hands"},
            {"kind": "material", "title": "Straw bales", "quantity": "120", "unit": "pieces", "category": str(category.pk)},
            {"kind": "skill", "title": ""},  # an empty row added and left alone
        ]),
    })
    project = Project.objects.get(title="Guest house")
    assert response.status_code == 302
    assert project.created_by == ambassador
    needs = list(project.needs.all())
    assert [n.title for n in needs] == ["Zimmerei", "Helping hands", "Straw bales"]
    assert needs[0].skill.slug == "carpentry"
    assert needs[1].skill is None  # not in the taxonomy: plain text, no new skill
    assert needs[2].skill is None
    # People are the unit of a skill need; only things get a gift category
    assert (needs[0].quantity, needs[0].unit, needs[0].category) == (2, "people", None)
    assert (needs[2].quantity, needs[2].unit, needs[2].category) == (120, "pieces", category)
    with translation.override("en"):
        assert needs[2].amount == "120 pieces"


@pytest.mark.django_db
def test_only_the_ambassador_creates_and_edits(community, project, helper):
    client = _client(helper)
    assert client.get(reverse("projects:create", args=[community.slug])).status_code == 403
    assert client.get(reverse("projects:edit", args=[project.pk])).status_code == 403
    assert client.post(reverse("projects:archive", args=[project.pk])).status_code == 403


@pytest.mark.django_db
def test_end_before_start_is_rejected(community, ambassador):
    response = _client(ambassador).post(reverse("projects:create", args=[community.slug]), {
        "title": "Backwards", "starts_on": "2030-03-01", "ends_on": "2030-02-01", **_formset([]),
    })
    assert response.status_code == 200
    assert not Project.objects.filter(title="Backwards").exists()


@pytest.mark.django_db
def test_editing_removes_needs_and_marks_the_project_fresh(project, ambassador):
    Project.objects.filter(pk=project.pk).update(updated_at=timezone.now() - timedelta(days=30))
    masonry, clay = project.needs.all()
    data = {
        "title": "Rocket stove", "starts_on": project.starts_on.isoformat(), "ends_on": project.ends_on.isoformat(),
        "needs-TOTAL_FORMS": "2", "needs-INITIAL_FORMS": "2", "needs-MIN_NUM_FORMS": "0", "needs-MAX_NUM_FORMS": "1000",
        "needs-0-id": masonry.pk, "needs-0-kind": "skill", "needs-0-title": "Masonry", "needs-0-DELETE": "on",
        "needs-1-id": clay.pk, "needs-1-kind": "material", "needs-1-title": "Clay", "needs-1-quantity": "300", "needs-1-unit": "kg",
    }
    assert _client(ambassador).post(reverse("projects:edit", args=[project.pk]), data).status_code == 302
    project.refresh_from_db()
    assert [(n.title, n.amount) for n in project.needs.all()] == [("Clay", "300 kg")]
    assert timezone.now() - project.updated_at < timedelta(minutes=1)


# ── Listing ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_shows_current_projects_only(community, project):
    today = timezone.localdate()
    Project.objects.create(community=community, title="Ongoing garden")
    Project.objects.create(community=community, title="Old roof", ends_on=today - timedelta(days=1))
    Project.objects.create(community=community, title="Shelved", archived_at=timezone.now())
    content = Client().get(reverse("projects:list")).content.decode()
    assert "Rocket stove" in content and "Ongoing garden" in content
    assert "Old roof" not in content and "Shelved" not in content


@pytest.mark.django_db
def test_list_filters_by_kind_of_open_need(community, project):
    Project.objects.create(community=community, title="Nothing needed")
    content = Client().get(reverse("projects:list"), {"kind": "material"}).content.decode()
    assert "Rocket stove" in content and "Nothing needed" not in content
    project.needs.filter(kind=Need.KIND_MATERIAL).update(covered_at=timezone.now())
    content = Client().get(reverse("projects:list"), {"kind": "material"}).content.decode()
    assert "Rocket stove" not in content


@pytest.mark.django_db
def test_community_page_shows_its_projects(community, project, ambassador):
    content = Client().get(community.get_absolute_url()).content.decode()
    assert "Rocket stove" in content
    assert reverse("projects:create", args=[community.slug]) not in content
    content = _client(ambassador).get(community.get_absolute_url()).content.decode()
    assert reverse("projects:create", args=[community.slug]) in content


# ── Offering help ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_offering_help_creates_a_stay_match_with_the_needs(project, helper, ambassador):
    masonry, clay = project.needs.all()
    response = _client(helper).post(reverse("projects:offer_help", args=[project.pk]), {
        f"need_{masonry.pk}": "on", f"need_{clay.pk}": "on", f"quantity_{clay.pk}": "50",
        "stay_from": project.starts_on.isoformat(), "stay_to": (project.starts_on + timedelta(days=6)).isoformat(),
        "message": "I can build and bring clay.",
    })
    match = Match.objects.get()
    assert response.status_code == 302 and response.url == match.get_absolute_url()
    assert match.target == project and match.recipient == ambassador and match.from_user == helper
    assert match.is_community_stay
    assert set(match.needs.all()) == {masonry, clay}
    assert {(o.need, o.quantity) for o in match.need_offers.all()} == {(masonry, None), (clay, 50)}
    assert match.stay_period() == (_aware(project.starts_on), _aware(project.starts_on + timedelta(days=6)))
    notification = Notification.objects.get(recipient=ambassador)
    assert notification.icon == "fa-person-digging"
    with translation.override("en"):
        assert notification.text == "Hugo offered to help with your project: Rocket stove"
    assert len(mail.outbox) == 1 and "Clay (50 kg)" in mail.outbox[0].body
    masonry.refresh_from_db()
    assert masonry.status == Need.STATUS_OFFERED


@pytest.mark.django_db
def test_no_offers_on_ended_projects_or_from_the_ambassador(project, helper, ambassador):
    assert _client(ambassador).get(reverse("projects:offer_help", args=[project.pk])).status_code == 302
    Project.objects.filter(pk=project.pk).update(archived_at=timezone.now())
    _client(helper).post(reverse("projects:offer_help", args=[project.pk]), {"message": "Hi"})
    assert not Match.objects.exists()


@pytest.mark.django_db
def test_need_status_follows_offers_and_the_ambassador(project, helper, ambassador):
    masonry = project.needs.get(title="Masonry")
    assert masonry.status == Need.STATUS_OPEN
    match = _offer(project, helper, needs=[masonry])
    assert Need.objects.get(pk=masonry.pk).status == Need.STATUS_OFFERED
    Match.objects.filter(pk=match.pk).update(status=Match.STATUS_ACCEPTED)
    masonry = Need.objects.get(pk=masonry.pk)
    assert masonry.status == Need.STATUS_PROMISED and masonry.promised_by() == [helper]

    url = reverse("projects:toggle_need", args=[project.pk, masonry.pk])
    _client(ambassador).post(url)
    assert Need.objects.get(pk=masonry.pk).status == Need.STATUS_COVERED
    _client(ambassador).post(url)
    assert Need.objects.get(pk=masonry.pk).covered_at is None


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
    project.needs.filter(title="Clay").update(covered_at=timezone.now())
    response = _client(ambassador).get(
        reverse("matches:calendar", args=[community.slug]), {"month": project.starts_on.strftime("%Y-%m")},
    )
    [(listed, needs)] = response.context["open_needs"]
    assert listed == project and [n.title for n in needs] == ["Masonry"]


@pytest.mark.django_db
def test_calendar_survives_a_bad_month(community, ambassador):
    response = _client(ambassador).get(reverse("matches:calendar", args=[community.slug]), {"month": "nope"})
    assert response.status_code == 200


# ── Freshness ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_ended_projects_are_archived_without_looking_updated(community):
    ended = Project.objects.create(community=community, title="Done", ends_on=timezone.localdate() - timedelta(days=1))
    updated_at = ended.updated_at
    assert archive_stale_projects() == (1, 0)
    ended.refresh_from_db()
    assert ended.archived_at is not None and ended.updated_at == updated_at


@pytest.mark.django_db
def test_stale_projects_are_asked_about_then_archived(community):
    stale = Project.objects.create(community=community, title="Garden")
    Project.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=61))

    assert archive_stale_projects() == (0, 1)
    assert mail.outbox[0].to == ["amb@example.com"]
    assert "Garden" in mail.outbox[0].subject and "noch aktuell" in mail.outbox[0].subject  # her language
    assert make_confirm_token(stale)[:10] in mail.outbox[0].body
    # Asked only once
    assert archive_stale_projects() == (0, 0)

    later = timezone.now() + timedelta(days=15)
    assert archive_stale_projects(now=later) == (1, 0)
    assert Project.objects.get(pk=stale.pk).archived_at is not None


@pytest.mark.django_db
def test_one_click_confirms_and_brings_back(community):
    stale = Project.objects.create(
        community=community, title="Garden", archived_at=timezone.now(), stale_reminder_sent_at=timezone.now(),
    )
    Project.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=80))
    response = Client().get(reverse("projects:confirm_by_email", args=[make_confirm_token(stale)]))
    assert response.status_code == 302
    stale.refresh_from_db()
    assert stale.archived_at is None and stale.stale_reminder_sent_at is None
    assert timezone.now() - stale.updated_at < timedelta(minutes=1)
    assert Client().get(reverse("projects:confirm_by_email", args=["forged"])).status_code == 400


@pytest.mark.django_db
def test_an_ended_project_is_not_brought_back_by_confirming(community, ambassador):
    ended = Project.objects.create(
        community=community, title="Done", ends_on=date(2020, 1, 1), archived_at=timezone.now(),
    )
    _client(ambassador).post(reverse("projects:confirm", args=[ended.pk]))
    assert Project.objects.get(pk=ended.pk).archived_at is not None


@pytest.mark.django_db
def test_last_seen_is_kept_up_to_date(helper):
    assert helper.last_active is None
    _client(helper).get(reverse("projects:list"))
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
    clay = project.needs.get(title="Clay")  # 200 kg
    first = _offer(project, helper, Match.STATUS_ACCEPTED)
    NeedOffer.objects.create(need=clay, match=first, quantity=120)
    clay = Need.objects.get(pk=clay.pk)
    assert clay.status == Need.STATUS_OFFERED and clay.remaining == 80
    with translation.override("en"):
        assert clay.progress == "120 of 200 kg promised"

    other = User.objects.create_user(email="other@example.com", password="x", name="Olu")
    second = _offer(project, other, Match.STATUS_PENDING)
    NeedOffer.objects.create(need=clay, match=second, quantity=80)
    assert Need.objects.get(pk=clay.pk).offered_quantity == 80
    Match.objects.filter(pk=second.pk).update(status=Match.STATUS_ACCEPTED)
    clay = Need.objects.get(pk=clay.pk)
    assert clay.status == Need.STATUS_PROMISED and clay.remaining == 0 and clay.progress == ""


@pytest.mark.django_db
def test_offer_form_only_lists_needs_still_missing(project, helper):
    masonry = project.needs.get(title="Masonry")
    match = _offer(project, helper, Match.STATUS_ACCEPTED)
    NeedOffer.objects.create(need=masonry, match=match)
    other = User.objects.create_user(email="other@example.com", password="x")
    response = _client(other).get(reverse("projects:offer_help", args=[project.pk]))
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
    project = mapped
    project.needs.filter(title="Masonry").update(covered_at=timezone.now())
    features = Client().get(reverse("gifts:api-markers")).json()["features"]
    [feature] = [f for f in features if f["properties"]["source"] == "need"]
    assert feature["properties"]["title"] == "Rocket stove"
    assert feature["properties"]["url"] == project.get_absolute_url()
    assert [n["title"] for n in feature["properties"]["needs"]] == ["Clay"]  # covered ones drop off
    assert feature["properties"]["needs"][0]["amount"] == "200 kg"

    # Only with the "need" type or no type filter; outside the viewport not at all
    assert not [f for f in Client().get(reverse("gifts:api-markers"), {"type": "offer"}).json()["features"]
                if f["properties"]["source"] == "need"]
    far = Client().get(reverse("gifts:api-markers"), {"bbox": "0,0,1,1"}).json()["features"]
    assert not [f for f in far if f["properties"]["source"] == "need"]


@pytest.mark.django_db
def test_gifts_filters_apply_to_needs(mapped):
    project = mapped
    building = ListingCategory.objects.create(name="Building Materials")
    tools = ListingCategory.objects.create(name="Tools")
    project.needs.filter(title="Clay").update(category=building)

    def needs_of(params):
        features = Client().get(reverse("gifts:api-markers"), params).json()["features"]
        return [n["title"] for f in features if f["properties"]["source"] == "need" for n in f["properties"]["needs"]]

    assert needs_of({"categories": building.pk}) == ["Clay"]
    assert needs_of({"categories": tools.pk}) == []
    assert needs_of({"search": "clay"}) == ["Clay"]
    assert needs_of({"search": "rocket"}) == ["Masonry", "Clay"]  # the project itself matches
    assert needs_of({"type": "need", "search": "nothing like it"}) == []


@pytest.mark.django_db
def test_project_needs_in_the_gifts_list(mapped):
    content = Client().get(reverse("gifts:api-list"), {"type": "need"}).content.decode()
    assert "Rocket stove" in content and "Clay" in content
    # Listing types alone leave them out
    assert "Rocket stove" not in Client().get(reverse("gifts:api-list"), {"type": "offer"}).content.decode()


@pytest.mark.django_db
def test_project_page_links_the_people_who_promised(project, helper):
    clay = project.needs.get(title="Clay")  # 200 kg
    match = _offer(project, helper, Match.STATUS_ACCEPTED)
    NeedOffer.objects.create(need=clay, match=match, quantity=120)
    with translation.override("en"):
        content = Client(HTTP_ACCEPT_LANGUAGE="en").get(project.get_absolute_url()).content.decode()
    assert "120 of 200 kg promised" in content
    assert f'<a href="{helper.get_absolute_url()}" class="underline hover:text-primary">Hugo</a> (120 kg)' in content
