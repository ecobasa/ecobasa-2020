import pytest
from pytest_django.asserts import assertRedirects

from django.test import Client

from ..models import User


@pytest.fixture
def user():
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.mark.django_db
class TestLoginView:
    def test_get(self, client: Client):
        response = client.get("/users/login")
        assert response.status_code == 200
        assert "Login" in str(response.content)

    def test_fail(self, client: Client, user: User):
        response = client.post(
            "/users/login", {"username": user.email, "password": "blabla"}, follow=True
        )
        assert response.status_code == 200
        assert "Sorry" in str(response.content)

    def test_login_email(self, client: Client, user: User):
        response = client.post(
            "/users/login", {"username": user.email, "password": "secret"}, follow=True
        )
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )

    def test_login_username(self, client: Client, user: User):
        response = client.post(
            "/users/login",
            {"username": user.username, "password": "secret"},
            follow=True,
        )
        assertRedirects(
            response, "/", status_code=302, target_status_code=200,
        )
