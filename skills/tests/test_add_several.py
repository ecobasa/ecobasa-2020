import pytest
from django.test import Client
from django.urls import reverse

from users.models import User
from gifts.models import Listing
from gifts.testing import skill_offer
from ..models import Skill


@pytest.fixture
def user(db):
    return User.objects.create_user(email="vol@example.com", password="secret", username="vol")


@pytest.fixture
def user_client(user):
    client = Client()
    client.login(username="vol@example.com", password="secret")
    return client


@pytest.fixture
def skills(db):
    return {slug: Skill.objects.create(name=slug.title(), slug=slug)
            for slug in ("carpentry", "cooking", "permaculture")}


URL = reverse("skills:userskill_add_several")


@pytest.mark.django_db
class TestUserskillAddSeveral:
    def test_requires_login(self, client):
        response = client.get(URL + "?offer=carpentry")
        assert response.status_code == 302
        assert "login" in response.url

    def test_lists_skills_not_yet_on_profile(self, user, user_client, skills):
        skill_offer(user, skills["cooking"])
        response = user_client.get(URL + "?offer=carpentry,cooking,unknown&wish=permaculture")
        assert response.status_code == 200
        assert [r["skill"].slug for r in response.context["offer_rows"]] == ["carpentry"]
        assert [r["skill"].slug for r in response.context["wish_rows"]] == ["permaculture"]
        assert b'name="level_offer_carpentry"' in response.content
        assert b'name="description_offer_carpentry"' in response.content

    def test_nothing_left_to_add_redirects_to_profile(self, user, user_client, skills):
        skill_offer(user, skills["cooking"])
        response = user_client.get(URL + "?offer=cooking")
        assert response.status_code == 302
        assert response.url == user.get_absolute_url()

    def test_adds_ticked_skills_with_levels(self, user, user_client, skills):
        response = user_client.post(URL, {
            "offer": ["carpentry"],               # cooking left unticked
            "level_offer_carpentry": "advanced",
            "description_offer_carpentry": "  Built our tiny house.  ",
            "level_offer_cooking": "expert",
            "wish": ["permaculture"],
            "level_wish_permaculture": "beginner",
        })
        assert response.status_code == 302
        assert response.url == user.get_absolute_url()
        assert list(Listing.objects.filter(type="offer", kind="skill", owner=user).values_list("skill__slug", "level")) == [("carpentry", "advanced")]
        assert list(Listing.objects.filter(type="wish", owner=user).values_list("skill__slug", "level")) == [("permaculture", "beginner")]
        assert Listing.objects.get(type="offer", kind="skill", owner=user).description == "Built our tiny house."
        assert Listing.objects.get(type="wish", owner=user).description == ""

    def test_ignores_invalid_level_and_existing_skill(self, user, user_client, skills):
        skill_offer(user, skills["cooking"], level="beginner")
        user_client.post(URL, {
            "offer": ["carpentry", "cooking"],
            "level_offer_carpentry": "grandmaster",
            "level_offer_cooking": "expert",
        })
        assert Listing.objects.get(type="offer", kind="skill", owner=user, skill=skills["carpentry"]).level == ""
        assert Listing.objects.get(type="offer", kind="skill", owner=user, skill=skills["cooking"]).level == "beginner"

    def test_taxonomy_skill_without_skill_row_is_created(self, user, user_client):
        from ..models import SkillTaxonomy
        SkillTaxonomy.objects.get_or_create(slug="fermentation-techniques",
                                            defaults={"names": {"en": "Fermentation techniques"}})
        Skill.objects.filter(slug="fermentation-techniques").delete()
        response = user_client.get(URL + "?offer=fermentation-techniques")
        assert [r["skill"].slug for r in response.context["offer_rows"]] == ["fermentation-techniques"]
        user_client.post(URL, {"offer": ["fermentation-techniques"], "level_offer_fermentation-techniques": "expert"})
        assert Listing.objects.get(type="offer", kind="skill", owner=user, skill__slug="fermentation-techniques").level == "expert"
