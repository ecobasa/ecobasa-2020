import pytest
from django.contrib.auth import authenticate

from ..models import User


class TestUser:
    user_credentials = {"email": "test@example.com", "password": "secret"}

    @pytest.mark.django_db
    def test_creation_and_auth(self):
        user = User.objects.create_user(**self.user_credentials)
        assert authenticate(**self.user_credentials) == user


@pytest.mark.django_db
class TestGetBySlug:
    def test_accented_name_resolves_from_its_url(self):
        user = User.objects.create_user(email="bjorn@example.com", name="Björn Achterberg")
        slug = user.get_absolute_url().rstrip("/").split("/")[-1]
        assert slug == "bjorn-achterberg"
        assert User.objects.get_by_slug(slug) == user

    def test_fully_accented_name(self):
        user = User.objects.create_user(email="zoe@example.com", name="Zoë")
        assert User.objects.get_by_slug("zoe") == user

    def test_username_then_pk(self):
        user = User.objects.create_user(email="max@example.com", username="max")
        assert User.objects.get_by_slug("max") == user
        assert User.objects.get_by_slug(str(user.pk)) == user

    def test_unknown_slug(self):
        assert User.objects.get_by_slug("nobody-here") is None
