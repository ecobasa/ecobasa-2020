import pytest

from django.test import Client
from django.utils import translation

from gift_economy.gifts.models import Listing
from users.models import User

from ..models import Match


@pytest.fixture
def owner():
    return User.objects.create_user(
        email="owner@example.com", password="secret", username="owner", name="Olga", language="de",
    )


@pytest.fixture
def requester():
    return User.objects.create_user(
        email="requester@example.com", password="secret", username="requester", name="Rafa", language="fr",
    )


@pytest.fixture
def match(owner, requester):
    listing = Listing.objects.create(title="Old Bicycle", type="offer", owner=owner)
    m = Match(from_user=requester, message="Interested!", recipient=owner)
    m.target = listing
    m.save()
    return m


def _client_for(user, language="en"):
    client = Client()
    client.login(username=user.email, password="secret")
    client.cookies["django_language"] = language
    return client


@pytest.mark.django_db
class TestMatchEmails:
    def test_request_email_is_in_the_recipients_language(self, owner, requester, mailoutbox):
        listing = Listing.objects.create(title="Lamp", type="offer", owner=owner)
        # the requester browses in French; the owner prefers German
        _client_for(requester, "fr").post(listing.get_absolute_url(), {
            "message": "Can I have it?", "location_type": Match.LOC_YOUR_PLACE,
        })
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [owner.email]
        assert mailoutbox[0].subject == "Rafa interessiert sich für dein Angebot: Lamp"
        assert "Hallo Olga," in mailoutbox[0].body
        assert "Annehmen" in mailoutbox[0].body

    def test_every_reply_is_emailed_with_its_text(self, owner, requester, match, mailoutbox):
        client = _client_for(requester, "en")
        client.post(match.get_absolute_url(), {"action": "message", "body": "Still free?"})
        client.post(match.get_absolute_url(), {"action": "message", "body": "Hello?"})

        assert [m.to for m in mailoutbox] == [[owner.email], [owner.email]]
        assert mailoutbox[0].subject == "Rafa hat dir eine Nachricht geschickt zu: Old Bicycle"
        assert "Still free?" in mailoutbox[0].body
        assert "Hello?" in mailoutbox[1].body

    def test_response_email_includes_the_note(self, owner, requester, match, mailoutbox):
        _client_for(owner, "de").post(match.get_absolute_url(), {"action": "accept", "body": "Come by Friday"})

        assert mailoutbox[0].to == [requester.email]
        assert mailoutbox[0].subject == "Olga a accepté ta demande : Old Bicycle"
        assert "Come by Friday" in mailoutbox[0].body

    def test_falls_back_to_site_language(self, owner, requester, match, mailoutbox):
        owner.language = ""
        owner.save()
        with translation.override("fr"):
            _client_for(requester, "fr").post(match.get_absolute_url(), {"action": "message", "body": "hi"})
        assert mailoutbox[0].subject == "Rafa sent you a message about: Old Bicycle"


@pytest.mark.django_db
class TestLanguagePreference:
    def test_language_switcher_saves_it_on_the_profile(self, owner):
        _client_for(owner).post("/i18n/setlang/", {"language": "es", "next": "/"})
        owner.refresh_from_db()
        assert owner.language == "es"

    def test_login_fills_in_a_missing_language(self):
        user = User.objects.create_user(email="new@example.com", password="secret", username="new")
        client = Client()
        client.cookies["django_language"] = "fr"
        client.post("/users/login/", {"username": "new@example.com", "password": "secret"})
        user.refresh_from_db()
        assert user.language == "fr"

    def test_login_on_a_new_device_switches_to_the_saved_language(self, owner):
        client = Client()
        client.cookies["django_language"] = "en"
        response = client.post("/users/login/", {"username": owner.email, "password": "secret"})
        assert response.cookies["django_language"].value == "de"

    def test_saved_language_wins_for_logged_in_users(self, owner):
        response = _client_for(owner, "fr").get("/")
        assert response.headers["Content-Language"] == "de"
        assert '<html lang="de"' in response.content.decode()

    def test_visitors_keep_their_cookie_language(self):
        client = Client()
        client.cookies["django_language"] = "fr"
        response = client.get("/")
        assert response.headers["Content-Language"] == "fr"
        assert "django_language" not in response.cookies
