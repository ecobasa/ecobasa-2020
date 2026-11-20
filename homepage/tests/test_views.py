import pytest

from django.test import Client


class TestHomepage:
    @pytest.mark.django_db
    def test_get(self, client: Client):
        response = client.get("/")
        assert response.status_code == 200
        assert "ecobasa" in str(response.content)
