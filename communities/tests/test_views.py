import pytest

from django.test import Client
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects

from users.models import User
from gift_economy.gifts.testing import need, skill_offer, skill_wish
from ..models import Community


@pytest.fixture
def user():
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.fixture
def community(user):
    return Community.objects.create(name="Test Community", ambassador=user)


@pytest.fixture
def user_client(db, user):
    """Return a client logged in as user"""
    client = Client()
    client.login(username=user.email, password="secret")
    return client


@pytest.mark.django_db
class TestDetail:
    def test_get(self, client: Client, community: Community):
        response = client.get(f"/communities/{community.slug}/")
        assert response.status_code == 200
        assert "Test Community" in str(response.content)

@pytest.mark.django_db
class TestVolunteerRequestSkillProposal:
    """After a volunteer request, skills not yet on the profile are offered for adding."""

    @pytest.fixture
    def volunteer_client(self, db):
        User.objects.create_user(email="vol@example.com", password="secret", username="vol")
        client = Client()
        client.login(username="vol@example.com", password="secret")
        return client

    def _send(self, client, community, **skills):
        return client.post(
            reverse("communities:volunteer_request", args=[community.slug]),
            {"volunteer_mode": "volunteer", "body": "Hello", **skills},
            HTTP_HX_REQUEST="true",
        )

    def test_one_skill_links_to_prefilled_skill_form(self, volunteer_client, community):
        from gift_economy.gifts.skills.models import Skill
        Skill.objects.create(name="Carpentry", slug="carpentry")
        response = self._send(volunteer_client, community, sender_skills="Carpentry")
        assert response.context["single_skill"] is True
        assert response.context["review_url"] == reverse("gifts:create") + "?skill=Carpentry&type=offer&kind=skill"

    def test_one_learning_goal_opens_form_in_wish_mode(self, volunteer_client, community):
        from gift_economy.gifts.skills.models import Skill
        Skill.objects.create(name="Permaculture", slug="permaculture")
        response = self._send(volunteer_client, community, practice_skills="Permaculture")
        assert response.context["review_url"].endswith("?skill=Permaculture&type=wish&kind=skill")

    def test_several_skills_link_to_add_several_page(self, volunteer_client, community):
        from gift_economy.gifts.skills.models import Skill
        Skill.objects.create(name="Carpentry", slug="carpentry")
        Skill.objects.create(name="Cooking", slug="cooking")
        Skill.objects.create(name="Permaculture", slug="permaculture")
        response = self._send(
            volunteer_client, community,
            sender_skills="Carpentry, Cooking", practice_skills="Permaculture",
        )
        assert response.context["single_skill"] is False
        assert response.context["review_url"] == (
            reverse("skills:userskill_add_several") + "?offer=carpentry%2Ccooking&wish=permaculture"
        )

    def test_no_prompt_when_skills_already_on_profile(self, volunteer_client, community):
        from gift_economy.gifts.skills.models import Skill
        skill = Skill.objects.create(name="Carpentry", slug="carpentry")
        skill_offer(User.objects.get(username="vol"), skill)
        response = self._send(volunteer_client, community, sender_skills="Carpentry")
        assert "review_url" not in response.context

    def test_skills_to_help_with_count_as_offers(self, volunteer_client, community):
        """Answering a community's wish, the practice field lists skills offered, not to learn."""
        from gift_economy.gifts.skills.models import Skill
        skill = Skill.objects.create(name="Nonviolent Communication", slug="nonviolent-communication")
        skill_offer(User.objects.get(username="vol"), skill)
        response = self._send(volunteer_client, community, volunteer_mode="wish",
                              practice_skills="Nonviolent Communication")
        assert "review_url" not in response.context

    def test_long_skill_lists_fit(self, volunteer_client, community):
        from gift_economy.matches.models import StayDetails
        many = ", ".join(f"Skill number {i}" for i in range(80))
        self._send(volunteer_client, community, sender_skills=many, practice_skills=many)
        assert StayDetails.objects.get().sender_skills == many


@pytest.mark.django_db
def test_volunteers_can_bring_what_the_community_needs(user, community):
    """The volunteer form offers the open needs of current projects and the community's
    wishes for things; what is ticked comes with the request, anything else is ignored."""
    from gift_economy.gifts.models import Listing
    from gift_economy.matches.models import Match
    from events.models import Event

    project = Event.objects.create(community=community, title="Rocket stove")
    clay = need(project, kind=Listing.KIND_MATERIAL, title="Clay")
    other_project = Event.objects.create(community=Community.objects.create(name="Elsewhere", ambassador=user), title="X")
    foreign = need(other_project, kind=Listing.KIND_TOOL, title="Spade")
    wish = Listing.objects.create(title="Wheelbarrow", type="wish", community=community)
    Listing.objects.create(title="Old bike", type="offer", community=community)
    Listing.objects.create(title="Hammock", type="wish", owner=user)  # the ambassador's own

    User.objects.create_user(email="vol@example.com", password="secret", username="vol")
    client = Client()
    client.login(username="vol@example.com", password="secret")

    context = client.get(community.get_absolute_url()).context
    assert context["bring_events"] == [(project, [clay])]
    assert context["bring_wishes"] == [wish]

    client.post(reverse("communities:volunteer_request", args=[community.slug]), {
        "body": "Hi", "need": [clay.pk, foreign.pk], "listing": [wish.pk, "nope"],
    })
    match = Match.objects.get()
    assert {c.listing for c in match.brings()} == {clay, wish}
    assert match.community == community

    # Shown with the stay on the volunteer visits page
    owner = Client()
    owner.login(username=user.email, password="secret")
    content = owner.get("/matches/?type=volunteer").content.decode()
    assert "Clay" in content and "Wheelbarrow" in content


@pytest.mark.django_db
def test_page_groups_offers_and_wishes(community):
    """Its offers come under one heading, its wishes for skills and things under another."""
    from gift_economy.gifts.models import Listing

    Listing.objects.create(title="Wheelbarrow", type="wish", community=community)
    Listing.objects.create(title="Hammock", type="wish", owner=community.ambassador)  # not the community's

    html = Client().get(community.get_absolute_url()).content.decode()
    assert 'id="wishes"' in html and "Things we wish for" in html
    assert "Wheelbarrow" in html and "Hammock" not in html
    assert 'id="offers"' not in html  # nothing on offer, and the visitor can't add any


@pytest.mark.django_db
def test_skill_fields_take_skills_from_the_list_only(user_client, community):
    """Every skill field is marked for the shared Tagify setup (users/_skill_tagify_js.html:
    suggestions, no free tags)."""
    for url, fields in (
        (reverse("communities:create"), 2),
        (reverse("communities:update", args=[community.slug]), 2),
        (reverse("events:create", args=[community.slug]), 1),
        (reverse("users:update"), 2),
    ):
        content = user_client.get(url).content.decode()
        assert content.count("data-skill-tags=") == fields, url
        assert "enforceWhitelist: true" in content, url
