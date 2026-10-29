from datetime import timedelta

import pytest
from django.contrib.gis.geos import Point
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone, translation

from communities.models import Community
from gift_economy.gifts.models import Listing, ListingCategory
from notifications.models import Notification
from projects.models import Project
from gift_economy.gifts.skills.models import Skill
from gift_economy.gifts.testing import need, skill_offer, skill_wish
from gift_economy.matches.models import Contribution
from users.models import User

from ..emails import make_suggestions_unsubscribe_token, send_suggestion_emails
from ..matching import match, match_everything
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


def _tag(listing):
    """What a listing is, in a word: a project's need, a skill (of a person or community),
    a wish for a skill, or another listing."""
    if listing.project_id and listing.is_wish:
        return "need"
    if listing.skill_id:
        if listing.is_wish:
            return "skillwish"
        return "communityskill" if listing.community_id else "userskill"
    return "listing"


def _pairs(user):
    return sorted((_tag(s.own), str(s.own), _tag(s.other), str(s.other), s.reason) for s in user.suggestions.all())


# ── What fits ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_gift_wish_and_offer_of_the_same_thing_are_suggested_to_both(anna, ben):
    wish = _listing(anna, "Scythe", "wish")
    offer = _listing(ben, "Two old scythes", "offer")
    created = match(offer, notify=False)
    assert len(created) == 2
    assert _pairs(anna) == [("listing", "Scythe", "listing", "Two old scythes", "thing")]
    assert _pairs(ben) == [("listing", "Two old scythes", "listing", "Scythe", "thing")]
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
    building = ListingCategory.objects.get(slug="building-renovation")
    wish = _listing(anna, "Wooden planks", "wish")
    wish.categories.add(building)
    offer = _listing(ben, "Firewood", "offer")
    offer.categories.add(building)
    community = Community.objects.create(name="Hof", owner=anna, location=GOERLITZ)
    project = Project.objects.create(community=community, title="Oven")
    need(project, kind=Listing.KIND_MATERIAL, title="Chimney pipe", category=building)
    assert match(offer, notify=False) == []

    need(project, kind=Listing.KIND_MATERIAL, title="Firewood for the kiln")
    match(offer, notify=False)
    assert ("need", "Firewood for the kiln", "listing", "Firewood", "thing") in _pairs(anna)


@pytest.mark.django_db
def test_things_not_in_the_vocabulary_match_by_similar_titles(anna, ben):
    _listing(anna, "Accordion", "wish")
    offer = _listing(ben, "Two old accordions", "offer")
    assert offer.thing is None
    match(offer, notify=False)
    assert _pairs(anna) == [("listing", "Accordion", "listing", "Two old accordions", "words")]


@pytest.mark.django_db
def test_things_match_in_any_language_and_by_broader_things(anna, ben):
    _listing(anna, "Leiter", "wish", kind=Listing.KIND_TOOL)
    _listing(anna, "Säge", "wish", kind=Listing.KIND_TOOL)
    _listing(anna, "Brennholz", "wish", kind=Listing.KIND_MATERIAL)
    match(_listing(ben, "Aluminium stepladder", "offer", kind=Listing.KIND_TOOL), notify=False)
    match(_listing(ben, "Jigsaw with blades", "offer", kind=Listing.KIND_TOOL), notify=False)
    match(_listing(ben, "Oak beams from a barn", "offer", kind=Listing.KIND_MATERIAL), notify=False)
    assert _pairs(anna) == [
        ("listing", "Leiter", "listing", "Aluminium stepladder", "thing"),
        ("listing", "Säge", "listing", "Jigsaw with blades", "thing"),
    ]


@pytest.mark.django_db
def test_a_material_does_not_fit_a_tool(anna, ben):
    wish = _listing(anna, "Wood saw", "wish", kind=Listing.KIND_TOOL)
    _listing(ben, "Sawdust from the wood workshop", "offer", kind=Listing.KIND_MATERIAL)
    other = _listing(ben, "Old wood saw", "offer")  # kind not given: may still fit
    match(wish, notify=False)
    assert [s.other for s in anna.suggestions.all()] == [other]


@pytest.mark.django_db
def test_skill_wishes_and_needs_meet_the_skills_of_people_and_communities(anna, ben):
    masonry = _skill("Masonry")
    wish = skill_wish(anna, masonry)
    community = Community.objects.create(name="Hof", owner=_user("amb@example.com", "Amb"), location=BAUTZEN)
    community_wish = skill_wish(community, masonry)
    project = Project.objects.create(community=community, title="Oven")
    project_need = need(project, kind=Listing.KIND_HANDS, title="Masonry", skill=masonry)
    teaching = skill_offer(community, masonry)

    user_skill = skill_offer(ben, masonry)
    match(user_skill, notify=False)
    # Ben hears about Anna's wish, the community's wish and the project
    assert {(_tag(s.other), s.other.pk) for s in ben.suggestions.all()} == {
        ("skillwish", wish.pk), ("skillwish", community_wish.pk), ("need", project_need.pk),
    }
    # Anna learns that Ben and the community offer it
    match(wish, notify=False)
    assert {(_tag(s.other), s.other.pk) for s in anna.suggestions.all()} == {
        ("userskill", user_skill.pk), ("communityskill", teaching.pk),
    }
    about_need = next(s for s in ben.suggestions.all() if s.other == project_need)
    about_teaching = next(s for s in anna.suggestions.all() if s.other == teaching)
    with translation.override("en"):
        assert about_need.text == "Oven at Hof needs: Masonry"
        assert about_teaching.text == "You can learn Masonry at Hof"
    # The title links the project to its page and the community to its profile,
    # the button leads to the offer form
    html = str(about_need.title_html)
    assert f'href="{project.get_absolute_url()}"' in html and f'href="{community.get_absolute_url()}"' in html
    assert about_need.url == f"{project.get_absolute_url()}#need-{project_need.pk}"
    assert about_need.action_url.endswith(f"/help/?need={project_need.pk}") and about_need.helps
    # A community's wish opens the volunteer form on its page
    about_community_wish = next(s for s in ben.suggestions.all() if s.other == community_wish)
    assert about_community_wish.action_url == f"{community.get_absolute_url()}?help={masonry.slug}" and about_community_wish.helps
    client = Client()
    client.force_login(ben)
    assert client.get(about_community_wish.action_url).context["help_wish"] == community_wish
    # Its title links the community's profile, only the button opens the form
    assert f'href="{community.get_absolute_url()}"' in str(about_community_wish.title_html)
    assert about_community_wish.url == community_wish.get_absolute_url()
    assert not about_teaching.helps


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
def test_searching_worldwide(anna, ben):
    far = _user("far@example.com", "Far", PARIS)  # ~900 km
    _listing(anna, "Clay", "wish")
    offer = _listing(far, "Clay from the Seine", "offer")
    assert match(offer, notify=False) == []

    anna.match_global = True
    anna.save()
    match(offer, notify=False)
    assert [s.other for s in anna.suggestions.all()] == [offer]
    assert not far.suggestions.exists()  # Far only looks 150 km around

    # Found from the far side too, when the worldwide one adds something
    far.match_global = True
    far.save()
    Suggestion.objects.all().delete()
    match(_listing(far, "Clay from the river", "offer"), notify=False)
    assert anna.suggestions.count() == 1 and far.suggestions.count() == 1


@pytest.mark.django_db
def test_profile_worldwide_switch(anna):
    client = Client()
    client.force_login(anna)
    data = {"name": "Anna", "match_emails": "on", "match_global": "on", "location": GOERLITZ.ewkt}
    assert client.post(reverse("users:update"), data).status_code == 302  # no distance sent: the field is disabled
    anna.refresh_from_db()
    assert anna.match_global and anna.match_radius == 150
    page = client.get(reverse("users:update")).content.decode()
    assert ':disabled="worldwide"' in page and "worldwide: true" in page


@pytest.mark.django_db
def test_nothing_between_own_things_too_far_unavailable_skills_or_covered_needs(anna, ben):
    far = _user("far@example.com", "Far", PARIS)
    _listing(anna, "Clay", "wish")
    assert match(_listing(anna, "Clay too", "offer"), notify=False) == []  # her own
    assert match(_listing(far, "Clay", "offer"), notify=False) == []  # 900 km

    masonry = _skill("Masonry")
    skill_wish(anna, masonry)
    assert match(skill_offer(ben, masonry, available=False), notify=False) == []

    community = Community.objects.create(name="Hof", owner=ben, location=BAUTZEN)
    project = Project.objects.create(community=community, title="Oven")
    covered = need(project, kind=Listing.KIND_MATERIAL, title="Clay", covered_at=timezone.now())
    assert match(covered, notify=False) == []


@pytest.mark.django_db
def test_without_a_place_or_country_it_is_anywhere_and_they_hear_how_to_narrow_it(anna):
    nowhere = User.objects.create_user(email="nowhere@example.com", password="x", name="Nowhere")
    far = _user("far@example.com", "Far", PARIS)
    _listing(nowhere, "Clay", "wish")
    match(_listing(far, "Clay from the Seine", "offer"), notify=True)
    # Nowhere hears about the offer in Paris; Far, who looks 150 km around, doesn't hear
    # about a wish without a place
    assert [s.other_user for s in nowhere.suggestions.all()] == [far]
    assert nowhere.suggestions.get().distance_km is None
    assert not far.suggestions.exists()
    area = Notification.objects.get(recipient=nowhere, tag=Notification.TAG_MATCH_AREA)
    assert area.link == reverse("users:update") + "#matches"
    # Only once
    match(_listing(anna, "Clay from the river", "offer"), notify=True)
    assert Notification.objects.filter(recipient=nowhere, tag=Notification.TAG_MATCH_AREA).count() == 1
    client = Client()
    client.force_login(nowhere)
    assert "because your profile has no place yet" in client.get(reverse("matches:list"), {"type": "gift", "box": "suggestions"}).content.decode()


@pytest.mark.django_db
def test_with_only_a_country_it_is_that_country(anna):
    german = User.objects.create_user(email="de@example.com", password="x", name="De", country="DE")
    french = User.objects.create_user(email="fr@example.com", password="x", name="Fr", country="FR")
    _listing(german, "Clay", "wish")
    _listing(french, "Clay", "wish")
    anna.country = "DE"
    anna.save()
    match(_listing(anna, "Clay from the pond", "offer"), notify=False)
    assert [s.other_user for s in german.suggestions.all()] == [anna]
    assert not french.suggestions.exists()
    # Unless they search worldwide
    french.match_global = True
    french.save()
    match(_listing(anna, "Clay from the river", "offer"), notify=False)
    assert french.suggestions.count() == 1


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
    assert notification.tag == Notification.TAG_SUGGESTION and notification.link == reverse("matches:list")
    with translation.override("en"):
        assert notification.text.startswith("1 new suggestion near you")

    # More matches bump the unread notification instead of adding one
    with django_capture_on_commit_callbacks(execute=True):
        _listing(ben, "Clay from the river", "offer")
    assert Notification.objects.filter(recipient=anna).count() == 1
    with translation.override("en"):
        assert Notification.objects.get(recipient=anna).text.startswith("2 new suggestions near you")


@pytest.mark.django_db
def test_moving_closer_matches_again(anna, ben, django_capture_on_commit_callbacks):
    far = _user("far@example.com", "Far", PARIS)
    masonry = _skill("Masonry")
    with django_capture_on_commit_callbacks(execute=True):
        skill_wish(anna, masonry)
        skill_offer(far, masonry)
        _listing(far, "Clay", "offer")
        _listing(anna, "Clay", "wish")
    assert not Suggestion.objects.exists()

    with django_capture_on_commit_callbacks(execute=True):
        far.location = BAUTZEN
        far.save()
    assert {_tag(s.other) for s in anna.suggestions.all()} == {"userskill", "listing"}
    assert Notification.objects.filter(recipient=anna, tag=Notification.TAG_SUGGESTION).exists()


@pytest.mark.django_db
def test_a_community_moving_closer_matches_its_skills_wishes_and_needs(anna, django_capture_on_commit_callbacks):
    masonry = _skill("Masonry")
    owner = _user("owner@example.com", "Owner", PARIS)
    community = Community.objects.create(name="Hof", owner=owner, location=PARIS)
    project = Project.objects.create(community=community, title="Oven")
    with django_capture_on_commit_callbacks(execute=True):
        skill_offer(anna, masonry)
        need(project, kind=Listing.KIND_HANDS, title="Masonry", skill=masonry)
    assert not anna.suggestions.exists()
    with django_capture_on_commit_callbacks(execute=True):
        community.location = BAUTZEN
        community.save()
    assert [_tag(s.other) for s in anna.suggestions.all()] == ["need"]


@pytest.mark.django_db
def test_saving_without_moving_does_not_match_again(anna, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        anna.name = "Anna B."
        anna.save()
    assert callbacks == []


@pytest.mark.django_db
def test_deleting_removes_its_suggestions(anna, ben):
    _listing(anna, "Clay", "wish")
    offer = _listing(ben, "Clay from the pond", "offer")
    match(offer, notify=False)
    offer.delete()
    assert not Suggestion.objects.exists()


@pytest.mark.django_db
def test_saving_the_profile_again_does_not_announce_the_same_wishes_again(anna, ben, django_capture_on_commit_callbacks):
    skill_offer(ben, _skill("Masonry"))
    data = {"name": "Anna", "skill_wishes": "Masonry", "match_emails": "on", "match_radius": "150",
            "location": GOERLITZ.ewkt}
    client = Client()
    client.force_login(anna)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(reverse("users:update"), data).status_code == 302
    wish = Listing.objects.get(owner=anna, type="wish")
    assert anna.suggestions.count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("users:update"), data)
    assert Listing.objects.get(owner=anna, type="wish") == wish  # kept, not removed and added again
    assert anna.suggestions.count() == 1


# ── The page ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_matches_page_shows_suggestions_first_by_type_marks_seen_and_hides(anna, ben):
    _listing(anna, "Clay", "wish")
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    client = Client()
    client.force_login(anna)

    response = client.get(reverse("matches:list"))
    tabs = {str(tab.label): tab for tab in response.context["tabs"]}
    assert tabs["Suggestions"].active and (tabs["Suggestions"].count, tabs["Suggestions"].waiting) == (1, 1)
    assert "Clay from the pond" in response.content.decode() and len(response.context["new_ids"]) == 1
    suggestion = anna.suggestions.get()
    assert suggestion.seen_at is not None and suggestion.kind == Suggestion.KIND_GIFT
    # Filtered by type
    assert client.get(reverse("matches:list"), {"type": "gift"}).context["suggestions"] == [suggestion]
    assert client.get(reverse("matches:list"), {"type": "skills"}).context["suggestions"] == []

    other = Client()
    other.force_login(ben)
    assert other.post(reverse("matches:dismiss_suggestion", args=[suggestion.pk])).status_code == 404
    url = reverse("matches:list") + "?type=gift"
    assert client.post(reverse("matches:dismiss_suggestion", args=[suggestion.pk]), {"next": url}).url == url
    assert "Clay from the pond" not in client.get(url).content.decode()


@pytest.mark.django_db
def test_project_needs_are_gifts_or_skills_by_what_they_need(anna, ben):
    masonry = _skill("Masonry")
    community = Community.objects.create(name="Hof", owner=anna, location=GOERLITZ)
    project = Project.objects.create(community=community, title="Oven")
    need(project, kind=Listing.KIND_HANDS, title="Masonry", skill=masonry)
    need(project, kind=Listing.KIND_MATERIAL, title="Clay")
    skill_wish(anna, masonry)
    match(skill_offer(ben, masonry), notify=False)
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    kinds = sorted((_tag(s.other), s.kind) for s in ben.suggestions.all())
    assert kinds == [("need", "gift"), ("need", "skills"), ("skillwish", "skills")]


# ── The weekly email ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_people_with_only_wishes_get_the_email_too(anna, ben):
    _listing(anna, "Clay", "wish")  # Anna only wishes
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    assert send_suggestion_emails() == 2
    to_anna = next(m for m in mail.outbox if m.to == ["anna@example.com"])
    assert to_anna.subject == "1 new suggestion near you"
    assert "Ben gives away: Clay from the pond" in to_anna.body and "List-Unsubscribe" in to_anna.extra_headers

    # Once a week, and only what's new
    assert send_suggestion_emails() == 0
    match(_listing(ben, "Clay from the river", "offer"), notify=False)
    assert send_suggestion_emails() == 0
    assert send_suggestion_emails(now=timezone.now() + timedelta(days=7)) >= 1
    later = [m for m in mail.outbox if m.to == ["anna@example.com"]][-1]
    assert "Clay from the river" in later.body and "Clay from the pond" not in later.body


@pytest.mark.django_db
def test_one_click_unsubscribe(anna, ben):
    response = Client().get(reverse("matches:suggestions_unsubscribe", args=[make_suggestions_unsubscribe_token(anna)]))
    assert response.status_code == 302
    anna.refresh_from_db()
    assert anna.match_emails is False
    _listing(anna, "Clay", "wish")
    match(_listing(ben, "Clay from the pond", "offer"), notify=False)
    assert send_suggestion_emails() == 1 and mail.outbox[0].to == ["ben@example.com"]
    assert Client().get(reverse("matches:suggestions_unsubscribe", args=["forged"])).status_code == 400


@pytest.mark.django_db
def test_match_everything_for_existing_data(anna, ben):
    _listing(anna, "Clay", "wish")
    _listing(ben, "Clay from the pond", "offer")
    assert match_everything() == 2
    assert not Notification.objects.exists()
    call_command("match_everything")
    assert Suggestion.objects.count() == 2
