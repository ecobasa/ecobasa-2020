import pytest

from django.test import Client
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects

from users.models import User
from ..models import Community


@pytest.fixture
def user():
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.fixture
def community(user):
    return Community.objects.create(name="Test Community", owner=user)


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
        from skills.models import Skill
        Skill.objects.create(name="Carpentry", slug="carpentry")
        response = self._send(volunteer_client, community, sender_skills="Carpentry")
        assert response.context["single_skill"] is True
        assert response.context["review_url"] == reverse("skills:userskill_add") + "?skill=Carpentry&mode=offer"

    def test_one_learning_goal_opens_form_in_wish_mode(self, volunteer_client, community):
        from skills.models import Skill
        Skill.objects.create(name="Permaculture", slug="permaculture")
        response = self._send(volunteer_client, community, practice_skills="Permaculture")
        assert response.context["review_url"].endswith("?skill=Permaculture&mode=wish")

    def test_several_skills_link_to_add_several_page(self, volunteer_client, community):
        from skills.models import Skill
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
        from skills.models import Skill, UserSkill
        skill = Skill.objects.create(name="Carpentry", slug="carpentry")
        UserSkill.objects.create(user=User.objects.get(username="vol"), skill=skill)
        response = self._send(volunteer_client, community, sender_skills="Carpentry")
        assert "review_url" not in response.context
