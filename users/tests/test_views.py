import re
from urllib.parse import urlparse

import pytest
from pytest_django.asserts import assertRedirects

from django.test import Client
from django.shortcuts import reverse
from django.urls import resolve
from django.contrib.auth import authenticate

from ..models import User


@pytest.fixture
def user() -> User:
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.fixture
def user_client(db, user) -> Client:
    """Return a client logged in as user"""
    client = Client()
    client.login(username=user.email, password="secret")
    return client


@pytest.mark.django_db
class TestLogin:
    def test_fail(self, client: Client, user: User):
        response = client.post(
            "/users/login/", {"username": user.email, "password": "blabla"}, follow=True
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_login_email(self, client: Client, user: User):
        response = client.post(
            "/users/login/", {"username": user.email, "password": "secret"}, follow=True
        )
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )

    def test_login_username(self, client: Client, user: User):
        response = client.post(
            "/users/login/",
            {"username": user.username, "password": "secret"},
            follow=True,
        )
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )


@pytest.mark.django_db
class TestRegister:
    def test_post_invalid(self, client: Client):
        response = client.post("/users/register/")
        assert response.status_code == 200
        assert not User.objects.all().exists()

    def test_redirect_if_logged_in(self, user_client: Client):
        response = user_client.get("/users/register/")
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )

    def test_post(self, client: Client):
        response = client.post(
            "/users/register/",
            {"first_name": "Max", "last_name": "Mustermann", "email": "max@mustermann.com", "password": "asdaogfisgaf"},
        )
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )
        assert User.objects.all().exists()


@pytest.mark.django_db
class TestPasswordReset:
    def test_pw_reset(self, client: Client, user: User, mailoutbox: list):
        # post email address
        res = client.post(
            reverse("users:password_reset"), {"email": user.email}, follow=True
        )
        assertRedirects(
            res,
            reverse("users:password_reset_done"),
            status_code=302,
            target_status_code=200,
        )

        # email send with correct link
        assert len(mailoutbox) == 1
        m = mailoutbox[0]
        url = re.search(r"(?P<url>https?://[^\s]+)", m.body).group("url")
        path = urlparse(url).path
        assert resolve(path).url_name == "password_reset_confirm"

        # get url from email
        res = client.get(path, follow=True)
        assert res.status_code == 200

        # post new password to url from email
        url, _ = res.redirect_chain[-1]
        new_password = "aseij0984ca0ara98h"
        res = client.post(
            url, {"new_password1": new_password, "new_password2": new_password}
        )
        assertRedirects(
            res,
            reverse("users:password_reset_complete"),
            status_code=302,
            target_status_code=200,
        )

        # check that new pw works
        newuser = authenticate(email=user.email, password=new_password)
        assert newuser == user


@pytest.mark.django_db
class TestMessageRecipientById:
    """Postman looks recipients up by id: names aren't unique and username is usually empty."""

    def test_profile_without_name_or_username_renders_message_link(self, user_client):
        nameless = User.objects.create_user(email="nameless@example.com", password="pw", name="")
        response = user_client.get(nameless.get_absolute_url())
        assert response.status_code == 200
        assert reverse("postman:write_with_recipients", args=[nameless.pk]) in response.content.decode()

    def test_autocomplete_returns_id_as_value(self, user_client):
        other = User.objects.create_user(email="ana@example.com", password="pw", name="Ana Costa")
        data = user_client.get(reverse("users:autocomplete"), {"q": "Ana"}).json()
        assert data[0]["value"] == str(other.pk)
        data = user_client.get(reverse("users:autocomplete"), {"id": other.pk}).json()
        assert data[0]["name"] == "Ana Costa"

    def test_message_reaches_only_that_user_when_names_collide(self, user_client):
        from postman.models import Message

        first = User.objects.create_user(email="arne1@example.com", password="pw", name="Arne")
        User.objects.create_user(email="arne2@example.com", password="pw", name="Arne")
        user_client.post(reverse("postman:write"), {"recipients": str(first.pk), "subject": "Hi", "body": "Hello"})
        assert list(Message.objects.values_list("recipient", flat=True)) == [first.pk]


@pytest.mark.django_db
class TestEmailChange:
    def _ask(self, client, email="maxi@example.org", password="secret"):
        return client.post(reverse("users:update"), {"new_email": email, "password": password})

    def _link(self, mailbox):
        return re.search(r"https?://\S+/users/email/\S+/", mailbox[0].body).group(0)

    def test_a_link_goes_to_the_new_address_and_nothing_changes_yet(self, user_client, user, mailoutbox):
        response = self._ask(user_client)
        assert response.status_code == 302
        assert [m.to for m in mailoutbox] == [["maxi@example.org"]]
        user.refresh_from_db()
        assert user.email == "max@mustermann.com"

    def test_wrong_password_taken_or_same_address(self, user_client, user, mailoutbox):
        User.objects.create_user(email="kim@example.org", password="secret", username="kim")
        assert self._ask(user_client, password="nope").status_code == 200
        assert self._ask(user_client, email="KIM@example.org").status_code == 200
        assert self._ask(user_client, email="max@mustermann.com").status_code == 200
        assert mailoutbox == []

    def test_opening_the_link_changes_nothing_until_confirmed(self, user_client, user, mailoutbox):
        self._ask(user_client)
        path = urlparse(self._link(mailoutbox)).path
        assert Client().get(path).status_code == 200
        user.refresh_from_db()
        assert user.email == "max@mustermann.com"

    def test_confirming_changes_the_login_and_tells_the_old_address(self, user_client, user, mailoutbox):
        self._ask(user_client)
        path = urlparse(self._link(mailoutbox)).path
        response = Client().post(path)
        assertRedirects(response, reverse("users:login"))
        user.refresh_from_db()
        assert user.email == "maxi@example.org"
        assert mailoutbox[-1].to == ["max@mustermann.com"]
        assert authenticate(username="maxi@example.org", password="secret") == user

    def test_the_link_works_only_once_and_not_once_the_address_is_taken(self, user_client, user, mailoutbox):
        self._ask(user_client)
        path = urlparse(self._link(mailoutbox)).path
        User.objects.create_user(email="maxi@example.org", password="secret", username="maxi")
        Client().post(path)
        user.refresh_from_db()
        assert user.email == "max@mustermann.com"
        User.objects.filter(username="maxi").delete()
        Client().post(path)
        Client().post(reverse("users:confirm_email", args=["broken"]))
        user.refresh_from_db()
        assert user.email == "maxi@example.org"
        assert user_client.post(path).status_code == 302
        assert len(mailoutbox) == 2
