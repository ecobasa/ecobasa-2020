from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone, translation

from communities.models import Community
from gifts.models import Listing, ListingCategory
from notifications.models import Notification
from projects.models import Need, Project
from skills.models import CommunitySkill, Skill, SkillWish, UserSkill
from users.models import User

from ..emails import make_unsubscribe_token, send_suggestion_emails
from ..engine import match, match_everything
from ..models import Suggestion

GOERLITZ = Point(14.9857, 51.1642, srid=4326)
BAUTZEN = Point(14.4290, 51.1810, srid=4326)  # ~39 km
PARIS = Point(2.35, 48.85, srid=4326)


@pytest.fixture(autouse=True)
def site(settings):
    settings.SITE_URL = "https://ecobasa.test"


def _user(email, name, point=GOERLITZ, **fields):
    return User.objects.create_user(email=email, password="x", name=name, location=point, **fields)


@pytest.fixture
def anna(db):
    return _user("anna@example.com", "Anna")


@pytest.fixture
def ben(db):
    return _user("ben@example.com", "Ben", BAUTZEN)


def _listing(owner, title, type, **fields):
    return Listing.objects.create(owner=owner, title=title, type=type, **fields)


def _skill(name):
    return Skill.objects.get_or_create(name=name)[0]


def _pairs(user):
    return sorted((s.own_type.model, str(s.own), s.other_type.model, str(s.other), s.reason) for s in user.suggestions.all())


# ── What fits ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_gift_wish_and_offer_with_similar_titles_are_suggested_to_both(anna, ben):
    wish = _listing(anna, "Scythe", "wish")
    offer = _listing(ben, "Two old scythes", "offer")
    created = match(offer, notify=False)
    assert len(created) == 2
    assert _pairs(anna) == [("listing", "Scythe", "listing", "Two old scythes", "words")]
    assert _pairs(ben) == [("listing", "Two old scythes", "listing", "Scythe", "words")]
    suggestion = anna.suggestions.get()
    assert 35 <= suggestion.distance_km <= 45 and suggestion.other_user == ben
    assert suggestion.url == offer.get_absolute_url()
    with translation.override("en"):
        assert suggestion.text == "Ben gives away: Two old scythes"
        assert suggestion.own_text == "your wish: Scythe"
        assert ben.suggestions.get().text == "Anna is looking for: Scythe"
    # Matching again finds nothing new
    assert match(wish, notify=False) == []


@pytest.mark.django_db
def test_things_match_by_title_not_by_gift_category(anna, ben):
    building = ListingCategory.objects.create(name="Building Materials")
    wish = _listing(anna, "Wooden planks", "wish")
    wish.categories.add(building)
    offer = _listing(ben, "Firewood", "offer")
    offer.categories.add(building)
    community = Community.objects.create(name="Hof", owner=anna, location=GOERLITZ)
    project = Project.objects.create(community=community, title="Oven")
    Need.objects.create(project=project, kind=Need.KIND_MATERIAL, title="Chimney pipe", category=building)
    assert match(offer, notify=False) == []

    Need.objects.create(project=project, kind=Need.KIND_MATERIAL, title="Firewood for the kiln")
    match(offer, notify=False)
    assert ("need", "Firewood for the kiln", "listing", "Firewood", "words") in _pairs(anna)


@pytest.mark.django_db
def test_skill_wishes_and_needs_meet_the_skills_of_people_and_communities(anna, ben):
    masonry = _skill("Masonry")
    wish = SkillWish.objects.create(user=anna, skill=masonry)
    community = Community.objects.create(name="Hof", owner=_user("amb@example.com", "Amb"), location=BAUTZEN)
    community_wish = SkillWish.objects.create(community=community, skill=masonry)
    project = Project.objects.create(community=community, title="Oven")
    need = Need.objects.create(project=project, kind=Need.KIND_SKILL, title="Masonry", skill=masonry)
    teaching = CommunitySkill.objects.create(community=community, skill=masonry)

    user_skill = UserSkill.objects.create(user=ben, skill=masonry)
    match(user_skill, notify=False)
    # Ben hears about Anna's wish, the community's wish and the project
    assert {(s.other_type.model, s.other.pk) for s in ben.suggestions.all()} == {
        ("skillwish", wish.pk), ("skillwish", community_wish.pk), ("need", need.pk),
    }
    # Anna learns that Ben and the community offer it
    match(wish, notify=False)
    assert {(s.other_type.model, s.other.pk) for s in anna.suggestions.all()} == {
        ("userskill", user_skill.pk), ("communityskill", teaching.pk),
    }
    about_need = next(s for s in ben.suggestions.all() if s.other == need)
    about_teaching = next(s for s in anna.suggestions.all() if s.other == teaching)
    with translation.override("en"):
        assert about_need.text == "Oven at Hof needs: Masonry"
        assert about_teaching.text == "You can learn Masonry at Hof"
    assert about_need.url.endswith(f"/help/?need={need.pk}")


@pytest.mark.django_db
def test_each_side_has_its_own_distance(anna, ben):
    anna.match_radius = 20
    anna.save()
    _listing(anna, "Clay", "wish")
    offer = _listing(ben, "Clay from the pond", "offer")
    match(offer, notify=False)
    assert not anna.suggestions.exists()  # 39 km is too far for her
    assert ben.suggestions.count() == 1


@pytest.mark.django_db
def test_nothing_without_a_place_between_own_things_unavailable_skills_or_covered_needs(anna, ben):
    far = _user("far@example.com", "Far", PARIS)
    nowhere = User.objects.create_user(email="nowhere@example.com", password="x")
    _listing(anna, "Clay", "wish")
    assert match(_listing(anna, "Clay too", "offer"), notify=False) == []  # her own
    assert match(_listing(far, "Clay", "offer"), notify=False) == []  # 900 km
    assert match(_listing(nowhere, "Clay", "offer"), notify=False) == []  # no place

    masonry = _skill("Masonry")
    SkillWish.objects.create(user=anna, skill=masonry)
    assert match(UserSkill.objects.create(user=ben, skill=masonry, available=False), notify=False) == []

    community = Community.objects.create(name="Hof", owner=ben, location=BAUTZEN)
    project = Project.objects.create(community=community, title="Oven")
    covered = Need.objects.create(project=project, kind=Need.KIND_MATERIAL, title="Clay", covered_at=timezone.now())
    assert match(covered, notify=False) == []


# ── Right after saving, with a notification ───────────────────────────


@pytest.mark.django_db
def test_saving_matches_and_notifies_right_away(anna, ben, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _listing(anna, "Clay", "wish")
    assert not Suggestion.objects.exists()

    with django_capture_on_commit_callbacks(execute=True):
        _listing(ben, "Clay from the pond", "offer")
    assert anna.suggestions.count() == 1 and ben.suggestions.count() == 1
    notification = Notification.objects.get(recipient=anna)
    assert notification.tag == Notification.TAG_SUGGESTION and notification.link == reverse("suggestions:list")
    with translation.override("en"):
        assert notification.text.startswith("1 new match near you")

    # More matches bump the unread notification instead of adding one
    with django_capture_on_commit_callbacks(execute=True):
        _listing(ben, "Clay bricks", "offer")
    assert Notification.objects.filter(recipient=anna).count() == 1
    with translation.override("en"):
        assert Notification.objects.get(recipient=anna).text.startswith("2 new matches near you")


@pytest.mark.django_db
def test_deleting_removes_its_suggestions(anna, ben):
    _listing(anna, "Clay", "wish")
    offer = _listing(ben, "Clay from the pond", "offer")
    match(offer, notify=False)
    offer.delete()
    assert not Suggestion.objects.exists()


@pytest.mark.django_db
def test_saving_the_profile_again_does_not_announce_the_same_wishes_again(anna, ben, django_capture_on_commit_callbacks):
    UserSkill.objects.create(user=ben, skill=_skill("Masonry"))
    data = {"name": "Anna", "skill_wishes": "Masonry", "match_emails": "on", "match_radius": "150",
            "location": GOERLITZ.ewkt}
    client = Client()
    client.force_login(anna)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(reverse("users:update"), data).status_code == 302
    wish = anna.skill_wishes.get()
    assert anna.suggestions.count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("users:update"), data)
    assert anna.skill_wishes.get() == wish  # kept, not removed and added again
    assert anna.suggestions.count() == 1


# ── The page ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_page_lists_marks_seen_and_hides(anna, ben):
    _listing(anna, "Clay", "wish")
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    client = Client()
    client.force_login(anna)
    response = client.get(reverse("suggestions:list"))
    assert "Clay from the pond" in response.content.decode() and len(response.context["new_ids"]) == 1
    suggestion = anna.suggestions.get()
    assert suggestion.seen_at is not None

    other = Client()
    other.force_login(ben)
    assert other.post(reverse("suggestions:dismiss", args=[suggestion.pk])).status_code == 404
    client.post(reverse("suggestions:dismiss", args=[suggestion.pk]))
    assert "Clay from the pond" not in client.get(reverse("suggestions:list")).content.decode()


# ── The weekly email ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_people_with_only_wishes_get_the_email_too(anna, ben):
    _listing(anna, "Clay", "wish")  # Anna only wishes
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    assert send_suggestion_emails() == 2
    to_anna = next(m for m in mail.outbox if m.to == ["anna@example.com"])
    assert to_anna.subject == "1 new match near you"
    assert "Ben gives away: Clay from the pond" in to_anna.body and "List-Unsubscribe" in to_anna.extra_headers

    # Once a week, and only what's new
    assert send_suggestion_emails() == 0
    match(_listing(ben, "Clay bricks", "offer"), notify=False)
    assert send_suggestion_emails() == 0
    assert send_suggestion_emails(now=timezone.now() + timedelta(days=7)) >= 1
    later = [m for m in mail.outbox if m.to == ["anna@example.com"]][-1]
    assert "Clay bricks" in later.body and "Clay from the pond" not in later.body


@pytest.mark.django_db
def test_one_click_unsubscribe(anna, ben):
    response = Client().get(reverse("suggestions:unsubscribe", args=[make_unsubscribe_token(anna)]))
    assert response.status_code == 302
    anna.refresh_from_db()
    assert anna.match_emails is False
    _listing(anna, "Clay", "wish")
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    assert send_suggestion_emails() == 1 and mail.outbox[0].to == ["ben@example.com"]
    assert Client().get(reverse("suggestions:unsubscribe", args=["forged"])).status_code == 400


@pytest.mark.django_db
def test_match_everything_for_existing_data(anna, ben):
    _listing(anna, "Clay", "wish")
    _listing(ben, "Clay from the pond", "offer")
    assert match_everything() == 2
    assert not Notification.objects.exists()
    call_command("match_everything")
    assert Suggestion.objects.count() == 2
