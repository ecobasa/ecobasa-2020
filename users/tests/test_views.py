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
    def test_get(self, client: Client):
        response = client.get("/users/login/")
        assert response.status_code == 200
        assert "Log in" in str(response.content)

    def test_fail(self, client: Client, user: User):
        response = client.post(
            "/users/login/", {"username": user.email, "password": "blabla"}, follow=True
        )
        assert response.status_code == 200
        assert "Credentials are not correct." in str(response.content)

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
    def test_get(self, client: Client):
        response = client.get("/users/register/")
        assert response.status_code == 200
        assert "Register" in str(response.content)

    def test_post_invalid(self, client: Client):
        response = client.post("/users/register/")
        assert response.status_code == 200
        assert "This field is required" in str(response.content)
        assert not User.objects.all().exists()

    def test_redirect_if_logged_in(self, user_client: Client):
        response = user_client.get("/users/register/")
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )

    def test_post(self, client: Client):
        response = client.post(
            "/users/register/",
            {"name": "Max", "email": "max@mustermann.com", "password": "asdaogfisgaf"},
        )
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )
        assert User.objects.all().exists()


@pytest.mark.django_db
class TestPasswordReset:
    def test_pw_reset(self, client: Client, user: User, mailoutbox: list):
        # get
        res = client.get(reverse("users:password_reset"))
        assert res.status_code == 200
        assert "Forgotten" in str(res.content)

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
        assert "Password reset" in m.subject
        url = re.search(r"(?P<url>https?://[^\s]+)", m.body).group("url")
        path = urlparse(url).path
        assert resolve(path).url_name == "password_reset_confirm"

        # get url from email
        res = client.get(path, follow=True)
        assert res.status_code == 200
        assert "form" in str(res.content)

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
