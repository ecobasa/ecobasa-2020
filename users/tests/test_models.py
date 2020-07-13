import pytest
from django.contrib.auth import authenticate

from ..models import User


class TestUser:
    user_credentials = {"email": "test@example.com", "password": "secret"}

    @pytest.mark.django_db
    def test_creation_and_auth(self):
        user = User.objects.create_user(**self.user_credentials)
        assert authenticate(**self.user_credentials) == user
