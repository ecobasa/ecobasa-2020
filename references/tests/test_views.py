import pytest

from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from communities.models import Community
from gifts.models import Listing
from matches.models import Match
from skills.models import CommunitySkill, Skill, UserSkill
from users.models import User

from ..models import Reference, ReferenceSkill


@pytest.fixture
def owner():
    return User.objects.create_user(email="owner@example.com", password="secret", username="owner", name="Owner")


@pytest.fixture
def author():
    return User.objects.create_user(email="author@example.com", password="secret", username="author")


@pytest.fixture
def listing(owner):
    return Listing.objects.create(title="Old Bicycle", type="offer", owner=owner)


@pytest.fixture
def community(owner):
    return Community.objects.create(name="Goat Farm", owner=owner)


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


def _save_url(subject):
    content_type = ContentType.objects.get_for_model(subject)
    return reverse("references:save", args=[content_type.pk, subject.pk])


@pytest.mark.django_db
class TestSaveReference:
    def test_about_a_user(self, author, owner):
        response = _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Lovely host."})
        assert response.status_code == 302
        assert response["Location"] == owner.get_absolute_url() + "#references"

        reference = Reference.objects.get()
        assert reference.author == author
        assert reference.recipient == owner
        assert reference.subject == owner
        assert reference.impression == Reference.IMPRESSION_POSITIVE

    def test_about_a_listing_goes_to_its_owner(self, author, owner, listing):
        _client_for(author).post(_save_url(listing), {"impression": "neutral", "text": "Fine."})
        reference = Reference.objects.get()
        assert reference.subject == listing
        assert reference.recipient == owner

    def test_about_a_community_goes_to_its_owner(self, author, owner, community):
        _client_for(author).post(_save_url(community), {"impression": "negative", "text": "Nobody was there."})
        assert Reference.objects.get().recipient == owner

    def test_second_save_updates_instead_of_duplicating(self, author, owner):
        client = _client_for(author)
        client.post(_save_url(owner), {"impression": "positive", "text": "First."})
        client.post(_save_url(owner), {"impression": "neutral", "text": "Second thoughts."})
        reference = Reference.objects.get()
        assert reference.impression == Reference.IMPRESSION_NEUTRAL
        assert reference.text == "Second thoughts."

    def test_not_about_yourself(self, owner, listing):
        client = _client_for(owner)
        assert client.post(_save_url(owner), {"impression": "positive", "text": "I'm great."}).status_code == 403
        assert client.post(_save_url(listing), {"impression": "positive", "text": "Mine."}).status_code == 403
        assert not Reference.objects.exists()

    def test_requires_login(self, owner):
        response = Client().post(_save_url(owner), {"impression": "positive", "text": "Hi."})
        assert response.status_code == 302
        assert not Reference.objects.exists()

    def test_unsupported_subject_type(self, author, owner):
        content_type = ContentType.objects.get_for_model(ContentType)
        url = reverse("references:save", args=[content_type.pk, content_type.pk])
        assert _client_for(author).post(url, {"impression": "positive", "text": "x"}).status_code == 404

    def test_empty_text_is_rejected(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": ""})
        assert not Reference.objects.exists()


@pytest.mark.django_db
class TestDeleteReference:
    def test_author_can_delete(self, author, owner):
        reference = Reference(author=author, recipient=owner, subject=owner, text="Hi.")
        reference.save()
        response = _client_for(author).post(reverse("references:delete", args=[reference.pk]))
        assert response.status_code == 302
        assert not Reference.objects.exists()

    def test_others_cannot_delete(self, author, owner):
        reference = Reference(author=author, recipient=owner, subject=owner, text="Hi.")
        reference.save()
        response = _client_for(owner).post(reverse("references:delete", args=[reference.pk]))
        assert response.status_code == 404
        assert Reference.objects.exists()


@pytest.mark.django_db
class TestReferencesSection:
    def test_listed_on_profile(self, author, owner):
        Reference(author=author, recipient=owner, subject=owner, text="Lovely host.").save()
        response = Client().get(owner.get_absolute_url())
        assert response.status_code == 200
        assert "Lovely host." in response.content.decode()

    def test_form_shown_to_others_but_not_owner(self, author, owner, listing):
        assert 'name="impression"' in _client_for(author).get(listing.get_absolute_url()).content.decode()
        assert 'name="impression"' not in _client_for(owner).get(listing.get_absolute_url()).content.decode()

    def test_rendered_on_community_page(self, community):
        assert 'id="references"' in Client().get(community.get_absolute_url()).content.decode()

    def test_profile_lists_references_about_their_listings_and_skills(self, author, owner, listing, community):
        Reference(author=author, recipient=owner, subject=listing, text="Bike was great.").save()
        Reference(author=author, recipient=owner, subject=community, text="Community stay.").save()
        content = Client().get(owner.get_absolute_url()).content.decode()
        assert "Bike was great." in content
        assert listing.get_absolute_url() in content
        # The community has its own page; its references don't belong to the owner personally
        assert "Community stay." not in content

    def test_reference_about_a_listing_does_not_count_as_own_profile_reference(self, author, owner, listing):
        Reference(author=author, recipient=owner, subject=listing, text="Bike was great.").save()
        content = _client_for(author).get(owner.get_absolute_url()).content.decode()
        assert "Write a reference" in content

    def test_community_page_lists_references_about_its_skills(self, author, owner, community):
        skill = Skill.objects.create(name="Cob building", slug="cob-building")
        community_skill = CommunitySkill.objects.create(community=community, skill=skill)
        Reference(author=author, recipient=owner, subject=community_skill, text="Learned a lot.").save()
        content = Client().get(community.get_absolute_url()).content.decode()
        assert "Learned a lot." in content
        assert community_skill.get_absolute_url() in content


@pytest.mark.django_db
class TestTagging:
    def _post(self, client, subject, **extra):
        data = {"impression": "positive", "text": "Great.", **extra}
        return client.post(_save_url(subject), data)

    def test_skill_the_person_has_is_confirmed_right_away(self, author, owner):
        skill = Skill.objects.create(name="Cob building", slug="cob-building")
        UserSkill.objects.create(user=owner, skill=skill)
        self._post(_client_for(author), owner, skill_names="Cob building")
        assert Reference.objects.get().skill_tags.get().status == ReferenceSkill.STATUS_CONFIRMED

    def test_new_skill_waits_until_the_person_confirms(self, author, owner):
        self._post(_client_for(author), owner, skill_names="Beekeeping")
        tag = ReferenceSkill.objects.get()
        assert tag.status == ReferenceSkill.STATUS_PENDING
        assert not UserSkill.objects.filter(user=owner).exists()

        # Only the person it is about can confirm
        url = reverse("references:skill_tag", args=[tag.pk, "confirm"])
        assert _client_for(author).post(url).status_code == 404
        _client_for(owner).post(url)
        tag.refresh_from_db()
        assert tag.status == ReferenceSkill.STATUS_CONFIRMED
        assert UserSkill.objects.filter(user=owner, skill=tag.skill).exists()

    def test_declined_skill_is_not_added(self, author, owner):
        self._post(_client_for(author), owner, skill_names="Beekeeping")
        tag = ReferenceSkill.objects.get()
        _client_for(owner).post(reverse("references:skill_tag", args=[tag.pk, "decline"]))
        tag.refresh_from_db()
        assert tag.status == ReferenceSkill.STATUS_DECLINED
        assert not UserSkill.objects.filter(user=owner).exists()

    def test_confirming_on_a_community_adds_a_community_skill(self, author, owner, community):
        self._post(_client_for(author), community, skill_names="Beekeeping")
        tag = ReferenceSkill.objects.get()
        _client_for(owner).post(reverse("references:skill_tag", args=[tag.pk, "confirm"]))
        assert CommunitySkill.objects.filter(community=community, skill=tag.skill).exists()

    def test_gift_names_are_kept_as_names_only(self, author, owner):
        self._post(_client_for(author), owner, gift_names=["Old Bicycle", " ", "Old Bicycle", "Tent"])
        assert Reference.objects.get().gift_names == ["Old Bicycle", "Tent"]

    def test_no_tags_on_references_about_a_listing(self, author, listing):
        self._post(_client_for(author), listing, skill_names="Beekeeping", gift_names=["Tent"])
        reference = Reference.objects.get()
        assert reference.gift_names == []
        assert not reference.skill_tags.exists()

    def test_editing_keeps_status_and_drops_removed_skills(self, author, owner):
        client = _client_for(author)
        self._post(client, owner, skill_names="Beekeeping, Carpentry")
        beekeeping = ReferenceSkill.objects.get(skill__name="Beekeeping")
        _client_for(owner).post(reverse("references:skill_tag", args=[beekeeping.pk, "confirm"]))
        self._post(client, owner, skill_names="Beekeeping")
        assert list(ReferenceSkill.objects.values_list("skill__name", "status")) == [
            ("Beekeeping", ReferenceSkill.STATUS_CONFIRMED)
        ]

    def test_confirmed_tag_shows_on_the_skill_page(self, author, owner):
        skill = Skill.objects.create(name="Cob building", slug="cob-building")
        user_skill = UserSkill.objects.create(user=owner, skill=skill)
        self._post(_client_for(author), owner, skill_names="Cob building", text="Built a wall together.")
        assert "Built a wall together." in Client().get(user_skill.get_absolute_url()).content.decode()

    def test_pending_tag_is_hidden_from_others(self, author, owner, listing):
        self._post(_client_for(author), owner, skill_names="Beekeeping")
        stranger = User.objects.create_user(email="s@example.com", password="secret", name="S")
        content = _client_for(stranger).get(owner.get_absolute_url()).content.decode()
        assert "Beekeeping" not in content


@pytest.mark.django_db
class TestReferenceFromMatch:
    def test_accepted_listing_match_links_to_owner_with_gift_name(self, author, owner, listing):
        match = Match(from_user=author, recipient=owner, message="Hi", status=Match.STATUS_ACCEPTED)
        match.target = listing
        match.save()
        content = _client_for(author).get(match.get_absolute_url()).content.decode()
        assert owner.get_absolute_url() + "?reference_gift=Old+Bicycle#references" in content

    def test_prefilled_gift_name_lands_in_the_form(self, author, owner):
        content = _client_for(author).get(owner.get_absolute_url() + "?reference_gift=Old+Bicycle").content.decode()
        assert "Old Bicycle" in content


@pytest.mark.django_db
class TestSkillSuggestions:
    def test_profile_skills_are_suggested_in_the_form(self, author, owner):
        skill = Skill.objects.create(name="Cob building", slug="cob-building")
        UserSkill.objects.create(user=owner, skill=skill)
        content = _client_for(author).get(owner.get_absolute_url()).content.decode()
        assert '<script id="reference-held-skills" type="application/json">["Cob Building"]</script>' in content

    def test_form_shows_the_writing_guide(self, author, owner):
        content = _client_for(author).get(owner.get_absolute_url()).content.decode()
        assert "How to write a reference" in content


@pytest.mark.django_db
class TestDashboard:
    def test_received_lists_references_about_me_my_listings_and_my_communities(self, author, owner, listing, community):
        Reference(author=author, recipient=owner, subject=owner, text="About the person.").save()
        Reference(author=author, recipient=owner, subject=listing, text="About the bicycle.").save()
        Reference(author=author, recipient=owner, subject=community, text="About the farm.").save()
        content = _client_for(owner).get(reverse("references:list")).content.decode()
        for text in ("About the person.", "About the bicycle.", "About the farm."):
            assert text in content

    def test_given_lists_what_i_wrote(self, author, owner):
        Reference(author=author, recipient=owner, subject=owner, text="Lovely host.").save()
        assert "Lovely host." in _client_for(author).get(reverse("references:list") + "?type=given").content.decode()
        assert "Lovely host." not in _client_for(author).get(reverse("references:list")).content.decode()

    def test_pending_skills_are_listed_and_counted(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        content = _client_for(owner).get(reverse("references:list")).content.decode()
        assert "Waiting for your confirmation" in content
        assert 'title="Waiting for your confirmation">1</span>' in content

    def test_confirming_from_the_dashboard_returns_there(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        tag = ReferenceSkill.objects.get()
        url = reverse("references:skill_tag", args=[tag.pk, "confirm"])
        response = _client_for(owner).post(url, {"next": reverse("references:list")})
        assert response["Location"] == reverse("references:list")
        # Foreign hosts are ignored
        tag.status = ReferenceSkill.STATUS_PENDING
        tag.save()
        response = _client_for(owner).post(url, {"next": "https://evil.example/"})
        assert response["Location"] == owner.get_absolute_url() + "#references"

    def test_requires_login(self):
        assert Client().get(reverse("references:list")).status_code == 302

    def test_edit_link_opens_the_form(self, author, owner):
        Reference(author=author, recipient=owner, subject=owner, text="Lovely host.").save()
        given = _client_for(author).get(reverse("references:list") + "?type=given").content.decode()
        assert owner.get_absolute_url() + "?edit_reference=1#references" in given
        page = _client_for(author).get(owner.get_absolute_url() + "?edit_reference=1").content.decode()
        assert "x-data=\"{ open: true" in page

    def test_community_guide_only_on_community_pages(self, author, owner, community):
        assert "Writing about a community" in _client_for(author).get(community.get_absolute_url()).content.decode()
        assert "Writing about a community" not in _client_for(author).get(owner.get_absolute_url()).content.decode()

    def test_received_is_grouped_by_owned_community(self, author, owner, community):
        Reference(author=author, recipient=owner, subject=community, text="About the farm.").save()
        content = _client_for(owner).get(reverse("references:list")).content.decode()
        about_you = content.index("About you")
        # The community header comes after "About you", and its reference after the header
        assert about_you < content.index("Goat Farm", about_you) < content.index("About the farm.")

    def test_given_does_not_ask_me_to_confirm_skills_i_tagged(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        content = _client_for(author).get(reverse("references:list") + "?type=given").content.decode()
        assert "Waiting for your confirmation</h3>" not in content
        assert "Add to my skills</button>" not in content
