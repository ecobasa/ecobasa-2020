from django.test import TestCase
from django.contrib.auth import authenticate

from ..models import User


class UserTestCase(TestCase):
    user_credentials = {"email": "test@example.com", "password": "secret"}

    def test_creation_and_auth(self):
        user = User.objects.create_user(**self.user_credentials)
        self.assertEqual(authenticate(**self.user_credentials), user)
