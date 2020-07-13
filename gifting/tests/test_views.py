import pytest

from django.test import Client

from ..models import Ad


@pytest.mark.django_db
class TestSearch:
    def test_get_empty(self, client: Client):
        response = client.get("/gifting/")
        assert response.status_code == 200
        assert "Find" in str(response.content)

    def test_get(self, client: Client):
        Ad.objects.create(title="Test", type="offer")
        Ad.objects.create(title="Foobar", type="wish")
        response = client.get("/gifting/")
        assert response.status_code == 200
        assert "Find" in str(response.content)

        assert len(response.context["ads"]) == 2
        assert "Test" in str(response.content)
        assert "Foobar" in str(response.content)


@pytest.mark.django_db
class TestDetail:
    def test_get(self, client: Client):
        ad = Ad.objects.create(title="Test", type="offer")
        response = client.get(f"/gifting/{ad.pk}")
        assert response.status_code == 200
        assert "Test" in str(response.content)
