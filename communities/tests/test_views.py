import pytest

from django.test import Client
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects

from users.models import User
from ..models import Community


@pytest.fixture
def user():
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.fixture
def community(user):
    return Community.objects.create(name="Test Community", owner=user)


@pytest.fixture
def user_client(db, user):
    """Return a client logged in as user"""
    client = Client()
    client.login(username=user.email, password="secret")
    return client


@pytest.mark.django_db
class TestDetail:
    def test_get(self, client: Client, community: Community):
        response = client.get(f"/communities/{community.slug}/")
        assert response.status_code == 200
        assert "Test Community" in str(response.content)