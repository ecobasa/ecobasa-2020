"""One model for every offer and wish: things, skills, knowledge, helping hands, a
community's and a project's."""

import pytest
from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone, translation

from communities.models import Community
from matches.matching import match
from matches.models import Contribution, Match
from projects.models import Project
from gifts.skills.models import Skill, SkillTaxonomy
from users.models import User

from ..models import Listing, skill_offers
from ..testing import need, skill_offer

GOERLITZ = Point(14.9857, 51.1642, srid=4326)


@pytest.fixture
def anna(db):
    return User.objects.create_user(email="anna@example.com", password="x", name="Anna", location=GOERLITZ)


@pytest.fixture
def ben(db):
    return User.objects.create_user(email="ben@example.com", password="x", name="Ben", location=GOERLITZ)


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _request(listing, user, quantity=None, status=Match.STATUS_PENDING):
    """`user` asks for an offer or answers a wish, taking or bringing `quantity` of it."""
    response = _client(user).post(listing.get_absolute_url(), {
        "message": "Hi", "location_type": Match.LOC_YOUR_PLACE, "quantity": quantity or "",
    })
    assert response.status_code == 302, response.context["form"].errors
    created = Match.objects.filter(from_user=user).latest("created_at")
    Match.objects.filter(pk=created.pk).update(status=status)
    return created


@pytest.mark.django_db
def test_a_gift_wish_is_covered_in_parts(anna, ben):
    clay = Listing.objects.create(owner=anna, type="wish", kind="material", title="Clay", quantity=200, unit="kg")
    first = _request(clay, ben, quantity=120)
    assert Contribution.objects.get(match=first).quantity == 120
    assert clay.status == Listing.STATUS_OFFERED

    Match.objects.filter(pk=first.pk).update(status=Match.STATUS_ACCEPTED)
    clay = Listing.objects.get(pk=clay.pk)
    with translation.override("en"):
        assert clay.progress == "120 of 200 kg promised"
    assert clay.remaining == 80 and Listing.objects.open().filter(pk=clay.pk).exists()

    _request(clay, User.objects.create_user(email="c@example.com", password="x"), quantity=80, status=Match.STATUS_ACCEPTED)
    clay = Listing.objects.get(pk=clay.pk)
    assert clay.status == Listing.STATUS_PROMISED and clay.is_done
    # Off the lists, and not matched any more
    assert not Listing.objects.open().filter(pk=clay.pk).exists()
    Listing.objects.create(owner=ben, type="offer", kind="material", title="Clay from our pond")
    assert match(clay, notify=False) == []


@pytest.mark.django_db
def test_an_offer_is_given_away_in_parts_but_a_skill_is_shared_again_and_again(anna, ben):
    firewood = Listing.objects.create(owner=anna, type="offer", kind="material", title="Firewood", quantity=3, unit="m3")
    _request(firewood, ben, quantity=3, status=Match.STATUS_ACCEPTED)
    assert Listing.objects.get(pk=firewood.pk).status == Listing.STATUS_PROMISED

    carpentry = skill_offer(anna, Skill.objects.create(name="Carpentry"))
    _request(carpentry, ben, status=Match.STATUS_ACCEPTED)
    carpentry = Listing.objects.get(pk=carpentry.pk)
    assert carpentry.status == Listing.STATUS_OFFERED and not carpentry.is_done
    assert Listing.objects.open().filter(pk=carpentry.pk).exists()


@pytest.mark.django_db
def test_wishes_for_knowledge_helping_hands_or_learning_a_skill(anna, ben):
    carpentry = Skill.objects.create(name="Carpentry")
    offer = skill_offer(ben, carpentry)
    # With a skill, each finds who has it
    for kind in (Listing.KIND_SKILL, Listing.KIND_KNOWLEDGE, Listing.KIND_HANDS):
        wish = Listing.objects.create(owner=anna, type="wish", kind=kind, skill=carpentry, title=f"{kind} wish")
        assert [s.other for s in match(wish, notify=False) if s.user == anna] == [offer]
        wish.delete()
    # Without one, helping hands meet helping hands by their words, not things
    hands = Listing.objects.create(owner=anna, type="wish", kind="hands", title="Hands for the harvest")
    Listing.objects.create(owner=ben, type="offer", kind="other", title="Harvest baskets")
    helper = Listing.objects.create(owner=ben, type="offer", kind="hands", title="I can help with any harvest")
    assert [s.other for s in match(hands, notify=False) if s.user == anna] == [helper]

    # Wanting to learn a skill stays open after someone taught it; knowledge is met
    learn = Listing.objects.create(owner=anna, type="wish", kind="skill", skill=carpentry)
    advice = Listing.objects.create(owner=anna, type="wish", kind="knowledge", title="Roof advice")
    for wish in (learn, advice):
        _request(wish, ben, status=Match.STATUS_ACCEPTED)
    assert not Listing.objects.get(pk=learn.pk).is_done
    assert Listing.objects.get(pk=advice.pk).is_done
    with translation.override("en"):
        assert learn.kind_label == "Learn a skill" and offer.kind_label == "Skill"


@pytest.mark.django_db
def test_the_form_makes_every_kind(anna):
    SkillTaxonomy.objects.create(names={"en": "Carpentry", "de": "Zimmerei"})
    client = _client(anna)
    # A skill named in any language; it is its title
    client.post(reverse("gifts:create"), {"type": "offer", "kind": "skill", "skill_name": "Zimmerei", "level": "advanced", "available": "on"})
    skill = Listing.objects.get(kind="skill")
    assert (skill.skill.slug, skill.display_title, skill.level, skill.owner) == ("carpentry", "Carpentry", "advanced", anna)
    # Knowledge needs a skill or words
    response = client.post(reverse("gifts:create"), {"type": "wish", "kind": "knowledge"})
    assert response.status_code == 200 and "title" in response.context["form"].errors
    client.post(reverse("gifts:create"), {"type": "wish", "kind": "knowledge", "title": "How to lime plaster"})
    assert Listing.objects.get(kind="knowledge").skill is None
    # A skill without a name, or a thing without a title, isn't saved
    assert "skill_name" in client.post(reverse("gifts:create"), {"type": "offer", "kind": "skill"}).context["form"].errors
    assert "title" in client.post(reverse("gifts:create"), {"type": "offer", "kind": "tool"}).context["form"].errors
    # Things keep no skill or level
    client.post(reverse("gifts:create"), {"type": "offer", "kind": "tool", "title": "Spade", "skill_name": "Zimmerei", "level": "expert"})
    spade = Listing.objects.get(title="Spade")
    assert spade.skill is None and spade.level == ""


@pytest.mark.django_db
def test_a_community_offers_and_wishes_through_its_ambassador(anna, ben):
    community = Community.objects.create(name="Hof", slug="hof", owner=anna, location=GOERLITZ)
    url = reverse("gifts:create") + "?community=hof"
    assert _client(ben).post(url, {"type": "wish", "kind": "material", "title": "Clay"}).status_code == 403
    _client(anna).post(url, {"type": "wish", "kind": "material", "title": "Clay", "community": "hof"})
    clay = Listing.objects.get(title="Clay")
    assert (clay.owner, clay.community, clay.manager, clay.holder) == (None, community, anna, community)
    assert clay.point == GOERLITZ  # where the community is
    assert clay in community.get_reference_subjects()
    # The ambassador edits it; the request for it goes to them
    assert _client(anna).get(clay.get_edit_url()).status_code == 200
    assert _client(ben).get(clay.get_edit_url()).status_code == 403
    request = _request(clay, ben)
    assert request.recipient == anna
    # It stays with the community when the ambassador changes
    community.owner = ben
    community.save()
    assert Listing.objects.get(pk=clay.pk).manager == ben


@pytest.mark.django_db
def test_a_projects_listings_are_listed_while_it_runs(anna, ben):
    community = Community.objects.create(name="Hof", owner=anna, location=GOERLITZ)
    project = Project.objects.create(community=community, title="Rocket stove")
    clay = need(project, "Clay", kind=Listing.KIND_MATERIAL)
    learn = skill_offer(community, Skill.objects.create(name="Masonry"), project=project)
    assert clay.community == community and clay.is_wish
    assert set(Listing.objects.current()) >= {clay, learn}
    assert learn in skill_offers(community).current()
    # Its need is helped with on the project's offer form
    content = _client(ben).get(clay.get_absolute_url()).content.decode()
    assert f"{reverse('projects:offer_help', args=[project.pk])}?need={clay.pk}" in content
    # Off the lists once it is over
    project.archived_at = timezone.now()
    project.save()
    assert not Listing.objects.current().filter(pk__in=[clay.pk, learn.pk]).exists()
    assert not Listing.objects.get(pk=clay.pk).is_current


@pytest.mark.django_db
def test_the_community_page_lists_its_and_its_members_skills_and_gifts_once(anna, ben):
    """A skill both the community and its member (the ambassador) offer shows once, as the
    community's; members' other offers are the community's gifts on offer."""
    community = Community.objects.create(name="Hof", slug="hof", owner=anna, location=GOERLITZ)
    baking = Skill.objects.create(name="Bread Baking", slug="bread-baking")
    ours = skill_offer(community, baking, level="advanced", description="Bake with us on Saturdays.")
    skill_offer(anna, baking)
    weaving = skill_offer(anna, Skill.objects.create(name="Weaving"))
    jam = Listing.objects.create(owner=anna, type="offer", kind="other", title="Plum jam")
    Listing.objects.create(owner=ben, type="offer", kind="other", title="Not a member's")

    context = _client(ben).get(community.get_absolute_url()).context
    assert [(listing, people) for listing, people in context["skills"]] == [(ours, [anna]), (weaving, [anna])]
    assert context["gifts"] == [jam]
    content = _client(ben).get(community.get_absolute_url()).content.decode()
    assert ours.get_absolute_url() in content and weaving.get_absolute_url() in content

    # Its page says the level and how to learn it, and leads to the volunteer form for it
    page = _client(ben).get(ours.get_absolute_url()).content.decode()
    assert "Bake with us on Saturdays." in page and "How you can learn it here" in page
    assert f"{community.get_absolute_url()}?learn=bread-baking" in page
    assert _client(ben).get(community.get_absolute_url(), {"learn": "bread-baking"}).context["learn_skill"] == ours


@pytest.mark.django_db
def test_a_projects_need_says_what_it_is_for(anna, ben):
    community = Community.objects.create(name="Hof", owner=anna, location=GOERLITZ)
    project = Project.objects.create(community=community, title="Rocket stove", starts_on=timezone.localdate())
    clay = need(project, "Clay", kind=Listing.KIND_MATERIAL)
    with translation.override("en"):
        page = _client(ben).get(clay.get_absolute_url()).content.decode()
    assert "needs this to realize their project" in page
    assert project.get_absolute_url() in page and community.get_absolute_url() in page


@pytest.mark.django_db
def test_the_kind_choices_have_their_icons_and_colours(anna):
    form = _client(anna).get(reverse("gifts:create")).context["form"]
    kinds = {radio.data["value"]: (icon, colour) for radio, icon, colour, _text in form.kind_radios()}
    assert kinds["skill"] == ("fa-graduation-cap", "bg-purple") and kinds["tool"] == ("fa-screwdriver-wrench", "bg-primary")
    assert [(icon, colour) for _radio, icon, colour, _text in form.type_radios()] == [("fa-gift", "bg-primary"), ("fa-heart", "bg-yellow")]
