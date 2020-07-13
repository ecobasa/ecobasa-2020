import pytest

from django.test import Client


class TestLoginView:
    @pytest.mark.django_db
    def test_get(self, client: Client):
        response = client.get("/users/login")
        assert response.status_code == 200
        assert "Login" in str(response.content)
