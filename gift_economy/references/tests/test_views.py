import pytest

from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from communities.models import Community
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match
from gift_economy.gifts.skills.models import Skill
from gift_economy.gifts.testing import skill_offer, skill_wish
from users.models import User

from ..models import Reference, ReferenceSkill


@pytest.fixture
def owner():
    return User.objects.create_user(email="owner@example.com", password="secret", username="owner", name="Owner")


@pytest.fixture
def author():
    return User.objects.create_user(email="author@example.com", password="secret", username="author", name="Ann")


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
        community_skill = skill_offer(community, skill)
        Reference(author=author, recipient=owner, subject=community_skill, text="Learned a lot.").save()
        content = Client().get(community.get_absolute_url()).content.decode()
        assert "Learned a lot." in content
        assert community_skill.get_absolute_url() in content

    def test_impression_counts_filter_the_list(self, author, owner):
        Reference(author=author, recipient=owner, subject=owner, text="Lovely host.").save()
        other = User.objects.create_user(email="other@example.com", password="secret", name="Bo")
        Reference(author=other, recipient=owner, subject=owner, impression="negative", text="Never answered.").save()
        content = Client().get(owner.get_absolute_url()).content.decode()
        assert "@click=\"shown = shown === 'positive' ? '' : 'positive'\"" in content
        assert "@click=\"shown = shown === 'negative' ? '' : 'negative'\"" in content
        assert "shown === 'neutral'" not in content  # no neutral ones, so no filter for them
        assert "x-show=\"!shown || shown === 'negative'\"" in content


@pytest.mark.django_db
class TestKindPill:
    """What a reference is about shows as a pill, like on match rows."""

    def test_from_its_match(self, author, owner, listing):
        listing.kind = Listing.KIND_TOOL
        listing.save()
        match = Match(from_user=author, recipient=owner, message="Hi", status=Match.STATUS_ACCEPTED)
        match.target = listing
        match.save()
        reference = Reference(author=author, recipient=owner, subject=owner, text="Thanks!", match=match)
        assert reference.kind == match.kind
        reference.save()
        assert "fa-screwdriver-wrench" in Client().get(owner.get_absolute_url()).content.decode()

    def test_from_its_subject(self, author, owner, listing, community):
        skill = skill_offer(owner, Skill.objects.create(name="Cob", slug="cob"))
        wish = Listing.objects.create(title="Scythe", type="wish", owner=owner)

        def kind(subject):
            return Reference(author=author, recipient=owner, subject=subject).kind[1:]

        assert kind(listing) == ("fa-gift", "bg-primary")
        assert kind(wish) == ("fa-hand-holding-heart", "bg-primary")
        assert kind(skill) == ("fa-graduation-cap", "bg-purple")
        assert kind(community) == (community.get_type_icon(), "bg-green")
        assert kind(owner) == ("fa-user", "bg-brown")

    def test_on_the_dashboard_and_homepage(self, author, owner):
        Reference(author=author, recipient=owner, subject=owner, text="Lovely host.",
                  share_publicly=True, featured_at=timezone.now()).save()
        assert 'fa-user mr-1"></i>Person' in _client_for(owner).get(reverse("references:list")).content.decode()
        assert 'fa-user mr-1"></i>Person' in Client().get("/").content.decode()


@pytest.mark.django_db
class TestTagging:
    def _post(self, client, subject, **extra):
        data = {"impression": "positive", "text": "Great.", **extra}
        return client.post(_save_url(subject), data)

    def test_skill_the_person_has_is_confirmed_right_away(self, author, owner):
        skill = Skill.objects.create(name="Cob building", slug="cob-building")
        skill_offer(owner, skill)
        self._post(_client_for(author), owner, skill_names="Cob building")
        assert Reference.objects.get().skill_tags.get().status == ReferenceSkill.STATUS_CONFIRMED

    def test_new_skill_waits_until_the_person_confirms(self, author, owner):
        self._post(_client_for(author), owner, skill_names="Beekeeping")
        tag = ReferenceSkill.objects.get()
        assert tag.status == ReferenceSkill.STATUS_PENDING
        assert not Listing.objects.filter(type="offer", kind="skill", owner=owner).exists()

        # Only the person it is about can confirm
        url = reverse("references:skill_tag", args=[tag.pk, "confirm"])
        assert _client_for(author).post(url).status_code == 404
        _client_for(owner).post(url)
        tag.refresh_from_db()
        assert tag.status == ReferenceSkill.STATUS_CONFIRMED
        assert Listing.objects.filter(type="offer", kind="skill", owner=owner, skill=tag.skill).exists()

    def test_declined_skill_is_not_added(self, author, owner):
        self._post(_client_for(author), owner, skill_names="Beekeeping")
        tag = ReferenceSkill.objects.get()
        _client_for(owner).post(reverse("references:skill_tag", args=[tag.pk, "decline"]))
        tag.refresh_from_db()
        assert tag.status == ReferenceSkill.STATUS_DECLINED
        assert not Listing.objects.filter(type="offer", kind="skill", owner=owner).exists()

    def test_confirming_on_a_community_adds_a_community_skill(self, author, owner, community):
        self._post(_client_for(author), community, skill_names="Beekeeping")
        tag = ReferenceSkill.objects.get()
        _client_for(owner).post(reverse("references:skill_tag", args=[tag.pk, "confirm"]))
        assert Listing.objects.filter(type="offer", kind="skill", community=community, skill=tag.skill).exists()

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
        user_skill = skill_offer(owner, skill)
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
        skill_offer(owner, skill)
        content = _client_for(author).get(owner.get_absolute_url()).content.decode()
        assert '<script id="reference-held-skills" type="application/json">["Cob Building"]</script>' in content

    def test_form_shows_the_writing_guide(self, author, owner):
        content = _client_for(author).get(owner.get_absolute_url()).content.decode()
        assert "How to write a reference" in content


@pytest.mark.django_db
class TestDashboard:
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
        assert "You are writing about a community" in _client_for(author).get(community.get_absolute_url()).content.decode()
        assert "You are writing about a community" not in _client_for(author).get(owner.get_absolute_url()).content.decode()

    def test_given_does_not_ask_me_to_confirm_skills_i_tagged(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        content = _client_for(author).get(reverse("references:list") + "?type=given").content.decode()
        assert "Waiting for your confirmation</h3>" not in content
        assert "Add to my skills</button>" not in content

    def test_pending_skill_links_to_its_reference(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        reference = Reference.objects.get()
        content = _client_for(owner).get(reverse("references:list")).content.decode()
        assert f'href="#reference-{reference.pk}"' in content
        assert f'id="reference-{reference.pk}"' in content

    def test_received_is_about_me_and_my_listings_not_my_communities(self, author, owner, listing, community):
        Reference(author=author, recipient=owner, subject=owner, text="About the person.").save()
        Reference(author=author, recipient=owner, subject=listing, text="About the bicycle.").save()
        Reference(author=author, recipient=owner, subject=community, text="About the farm.").save()
        content = _client_for(owner).get(reverse("references:list")).content.decode()
        assert "About the person." in content and "About the bicycle." in content
        assert "About the farm." not in content

    def test_ambassador_sees_community_references_on_their_own_page(self, author, owner, community):
        Reference(author=author, recipient=owner, subject=community, text="About the farm.").save()
        url = reverse("references:list") + f"?community={community.slug}"
        content = _client_for(owner).get(url).content.decode()
        assert "About the farm." in content
        assert "ambassador of Goat Farm" in content
        # The sidebar links to it
        assert f"?community={community.slug}" in _client_for(owner).get(reverse("references:list")).content.decode()

    def test_only_the_ambassador_sees_the_community_page(self, author, community):
        url = reverse("references:list") + f"?community={community.slug}"
        assert _client_for(author).get(url).status_code == 404

    def test_community_pending_skills_count_separately(self, author, owner, community):
        _client_for(author).post(_save_url(community), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        received = _client_for(owner).get(reverse("references:list")).content.decode()
        assert "Waiting for your confirmation</h3>" not in received
        page = _client_for(owner).get(reverse("references:list") + f"?community={community.slug}").content.decode()
        assert "Add to the community's skills" in page


    def test_received_and_given_are_tabs_with_counts(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Lovely host."})
        tabs = _client_for(author).get(reverse("references:list") + "?type=given").context["tabs"]
        assert [(str(t.label), t.count, t.active) for t in tabs] == [("Received", 0, False), ("Given", 1, True)]

    def test_long_lists_are_paged(self, author, owner):
        from dashboard_lists import PER_PAGE
        for i in range(PER_PAGE + 1):
            Reference.objects.create(author=User.objects.create_user(
                email=f"a{i}@example.com", password="secret", username=f"a{i}"), subject=owner, text=f"Ref {i}")
        client = _client_for(owner)
        first = client.get(reverse("references:list")).context["page"]
        assert len(first.object_list) == PER_PAGE and first.older_url.endswith("page=2")
        assert len(client.get(first.older_url).context["page"].object_list) == 1


@pytest.mark.django_db
class TestNotifications:
    def _notifications(self, user):
        from notifications.models import Notification
        return Notification.objects.filter(recipient=user, tag=Notification.TAG_REFERENCE)

    def test_new_reference_about_you(self, author, owner):
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great."})
        reference = Reference.objects.get()
        notification = self._notifications(owner).get()
        assert notification.text == "Ann wrote a reference about you."
        assert notification.link == reverse("references:list") + f"#reference-{reference.pk}"

    def test_about_your_listing(self, author, owner, listing):
        _client_for(author).post(_save_url(listing), {"impression": "neutral", "text": "Fine."})
        assert self._notifications(owner).get().text == "Ann wrote a reference about Old Bicycle."

    def test_ambassador_gets_community_references(self, author, owner, community):
        _client_for(author).post(_save_url(community), {"impression": "positive", "text": "Great.", "skill_names": "Beekeeping"})
        notification = self._notifications(owner).get()
        assert notification.text == (
            "Ann wrote a reference about Goat Farm. It mentions skills that wait for your confirmation."
        )
        assert notification.link.startswith(reverse("references:list") + f"?community={community.slug}#reference-")

    def test_editing_does_not_notify_again(self, author, owner):
        client = _client_for(author)
        client.post(_save_url(owner), {"impression": "positive", "text": "Great."})
        client.post(_save_url(owner), {"impression": "neutral", "text": "Second thoughts."})
        assert self._notifications(owner).count() == 1

    def test_shown_in_the_readers_language(self, author, owner):
        from django.utils import translation
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Great."})
        notification = self._notifications(owner).get()
        with translation.override("de"):
            assert notification.text == "Ann hat eine Referenz über dich geschrieben."


@pytest.mark.django_db
class TestEmails:
    def test_email_in_the_recipients_language(self, author, owner):
        from django.core import mail
        owner.language = "de"
        owner.save()
        _client_for(author).post(_save_url(owner), {"impression": "positive", "text": "Lovely host.", "gift_names": ["Tent"]})
        email = mail.outbox[-1]
        assert email.to == [owner.email]
        assert email.subject == "Ann hat eine Referenz über dich geschrieben."
        assert "Lovely host." in email.body and "Tent" in email.body
        assert "Referenz ansehen" in email.alternatives[0][0]

    def test_ambassador_email_for_a_community(self, author, owner, community):
        from django.core import mail
        _client_for(author).post(_save_url(community), {"impression": "positive", "text": "Great farm."})
        email = mail.outbox[-1]
        assert email.to == [owner.email]
        assert "You receive this as ambassador of Goat Farm." in email.body
        assert f"?community={community.slug}#reference-" in email.body

    def test_editing_sends_no_email(self, author, owner):
        from django.core import mail
        client = _client_for(author)
        client.post(_save_url(owner), {"impression": "positive", "text": "Great."})
        sent = len(mail.outbox)
        client.post(_save_url(owner), {"impression": "neutral", "text": "Second thoughts."})
        assert len(mail.outbox) == sent

    def test_user_menu_lists_references_and_community_references(self, author, owner, community):
        content = _client_for(owner).get("/").content.decode()
        assert f'href="{reverse("references:list")}"' in content
        assert f'href="{reverse("references:list")}?community={community.slug}"' in content
        # Not ambassador of any community: no community entries
        assert "?community=" not in _client_for(author).get("/").content.decode()
