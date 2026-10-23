import pytest

from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from communities.models import Community
from gifts.models import Listing
from users.models import User

from ..models import Reference


@pytest.fixture
def owner():
    return User.objects.create_user(email="owner@example.com", password="secret", username="owner")


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
        response = _client_for(author).post(_save_url(owner), {"tone": "positive", "text": "Lovely host."})
        assert response.status_code == 302
        assert response["Location"] == owner.get_absolute_url() + "#references"

        reference = Reference.objects.get()
        assert reference.author == author
        assert reference.recipient == owner
        assert reference.subject == owner
        assert reference.tone == Reference.TONE_POSITIVE

    def test_about_a_listing_goes_to_its_owner(self, author, owner, listing):
        _client_for(author).post(_save_url(listing), {"tone": "neutral", "text": "Fine."})
        reference = Reference.objects.get()
        assert reference.subject == listing
        assert reference.recipient == owner

    def test_about_a_community_goes_to_its_owner(self, author, owner, community):
        _client_for(author).post(_save_url(community), {"tone": "negative", "text": "Nobody was there."})
        assert Reference.objects.get().recipient == owner

    def test_second_save_updates_instead_of_duplicating(self, author, owner):
        client = _client_for(author)
        client.post(_save_url(owner), {"tone": "positive", "text": "First."})
        client.post(_save_url(owner), {"tone": "neutral", "text": "Second thoughts."})
        reference = Reference.objects.get()
        assert reference.tone == Reference.TONE_NEUTRAL
        assert reference.text == "Second thoughts."

    def test_not_about_yourself(self, owner, listing):
        client = _client_for(owner)
        assert client.post(_save_url(owner), {"tone": "positive", "text": "I'm great."}).status_code == 403
        assert client.post(_save_url(listing), {"tone": "positive", "text": "Mine."}).status_code == 403
        assert not Reference.objects.exists()

    def test_requires_login(self, owner):
        response = Client().post(_save_url(owner), {"tone": "positive", "text": "Hi."})
        assert response.status_code == 302
        assert not Reference.objects.exists()

    def test_unsupported_subject_type(self, author, owner):
        content_type = ContentType.objects.get_for_model(ContentType)
        url = reverse("references:save", args=[content_type.pk, content_type.pk])
        assert _client_for(author).post(url, {"tone": "positive", "text": "x"}).status_code == 404

    def test_empty_text_is_rejected(self, author, owner):
        _client_for(author).post(_save_url(owner), {"tone": "positive", "text": ""})
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
        assert 'name="tone"' in _client_for(author).get(listing.get_absolute_url()).content.decode()
        assert 'name="tone"' not in _client_for(owner).get(listing.get_absolute_url()).content.decode()

    def test_rendered_on_community_page(self, community):
        assert 'id="references"' in Client().get(community.get_absolute_url()).content.decode()
