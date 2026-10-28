import pytest

from django.utils import translation

from users.models import User
from users.forms import ProfileUpdateForm
from gift_economy.gifts.models import Listing
from ..skills.models import Skill, SkillTaxonomy, get_or_create_skill, skill_name_q


@pytest.fixture
def carpentry(db):
    return SkillTaxonomy.objects.create(
        slug="test-carpentry",
        names={"en": "Test Carpentry", "de": "Test-Zimmerei", "es": "Carpintería de prueba", "fr": "Menuiserie test"},
    )


@pytest.mark.django_db
class TestSkillTaxonomyLink:
    def test_names_in_any_language_resolve_to_one_skill(self, carpentry):
        en, created = get_or_create_skill("Test Carpentry")
        de, _ = get_or_create_skill("test-zimmerei")
        fr, _ = get_or_create_skill("Menuiserie test")
        assert created
        assert en.pk == de.pk == fr.pk
        assert en.name == "Test Carpentry"
        assert en.slug == "test-carpentry"
        assert Skill.objects.filter(slug="test-carpentry").count() == 1

    def test_resolve_by_slug(self, carpentry):
        skill, _ = get_or_create_skill(slug="test-carpentry")
        assert skill.name == "Test Carpentry"

    def test_unknown_name_falls_back_to_plain_skill(self, db):
        skill, created = get_or_create_skill("Underwater Basket Weaving")
        assert created and skill.name == "Underwater Basket Weaving"
        assert str(skill) == "Underwater Basket Weaving"

    def test_display_name_follows_active_language(self, carpentry):
        skill, _ = get_or_create_skill("Test Carpentry")
        with translation.override("de"):
            assert str(skill) == "Test-Zimmerei"
        with translation.override("fr"):
            assert skill.get_name() == "Menuiserie test"
        assert skill.get_name("es") == "Carpintería de prueba"

    def test_search_matches_names_in_other_languages(self, carpentry):
        skill, _ = get_or_create_skill("Test Carpentry")
        assert list(Skill.objects.filter(skill_name_q("Zimmerei", ""))) == [skill]

    def test_profile_form_saves_german_name_as_canonical_skill(self, carpentry):
        user = User.objects.create_user(email="anna@example.com", password="secret", username="anna")
        form = ProfileUpdateForm(
            data={"name": "Anna", "skills": "Test-Zimmerei", "skill_wishes": ""},
            instance=user,
        )
        assert form.is_valid(), form.errors
        form.save()
        assert list(Listing.objects.filter(owner=user, type="offer").values_list("skill__slug", flat=True)) == ["test-carpentry"]
