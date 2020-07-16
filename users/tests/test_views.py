import pytest
from pytest_django.asserts import assertRedirects

from django.test import Client

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
        assert "Login" in str(response.content)

    def test_fail(self, client: Client, user: User):
        response = client.post(
            "/users/login/", {"username": user.email, "password": "blabla"}, follow=True
        )
        assert response.status_code == 200
        assert "Sorry" in str(response.content)

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
