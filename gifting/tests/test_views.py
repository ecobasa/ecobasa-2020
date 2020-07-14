import pytest

from django.test import Client
from pytest_django.asserts import assertRedirects

from ..models import Ad


@pytest.fixture
def ads():
    return [
        Ad.objects.create(title="Test", type="offer", description="testdesc"),
        Ad.objects.create(title="Foobar", type="wish", description="foobardesc"),
    ]


@pytest.fixture
def ad():
    return Ad.objects.create(type="offer", title="test")


@pytest.mark.django_db
class TestSearch:
    def test_get_empty(self, client: Client):
        response = client.get("/gifting/")
        assert response.status_code == 200

    def test_get(self, client: Client, ads: [Ad]):
        response = client.get("/gifting/")
        assert response.status_code == 200
        assert "Test" in str(response.content)
        assert "Foobar" in str(response.content)

    def test_filter_by_type(self, client: Client, ads: [Ad]):
        response = client.get("/gifting/?type=offer")
        assert "Test" in str(response.content)
        assert "Foobar" not in str(response.content)

        response = client.get("/gifting/?type=wish")
        assert "Test" not in str(response.content)
        assert "Foobar" in str(response.content)

    def test_filter_search(self, client: Client, ads: [Ad]):
        response = client.get("/gifting/?search=testdesc")
        assert "Test" in str(response.content)
        assert "Foobar" not in str(response.content)

        response = client.get("/gifting/?search=foobardesc")
        assert "Test" not in str(response.content)
        assert "Foobar" in str(response.content)


@pytest.mark.django_db
class TestDetail:
    def test_get(self, client: Client, ad: Ad):
        response = client.get(f"/gifting/{ad.pk}")
        assert response.status_code == 200
        assert "test" in str(response.content)


@pytest.mark.django_db
class TestCreate:
    def test_get(self, client: Client):
        response = client.get("/gifting/create")
        assert response.status_code == 200

    def test_post_invalid(self, client: Client):
        response = client.post("/gifting/create")
        assert response.status_code == 200
        assert "This field is required." in str(response.content)

    def test_post_valid(self, client: Client):
        response = client.post(
            "/gifting/create", {"type": "offer", "title": "new test offer"}, follow=True
        )
        assert Ad.objects.count() == 1
        assertRedirects(
            response,
            Ad.objects.get().get_absolute_url(),
            status_code=302,
            target_status_code=200,
        )
        assert "new test offer" in str(response.content)


@pytest.mark.django_db
class TestEdit:
    def test_get(self, client: Client, ad: Ad):
        response = client.get(f"/gifting/{ad.pk}/edit")
        assert response.status_code == 200

    def test_404(self, client: Client, ad: Ad):
        response = client.get("/gifting/abcdefgh/edit")
        assert response.status_code == 404

    def test_post_invalid(self, client: Client, ad: Ad):
        response = client.post(f"/gifting/{ad.pk}/edit")
        assert response.status_code == 200
        assert "This field is required." in str(response.content)

    def test_post_valid(self, client: Client, ad: Ad):
        assert Ad.objects.count() == 1
        response = client.post(
            f"/gifting/{ad.pk}/edit",
            {"type": "offer", "title": "new test offer"},
            follow=True,
        )
        assert Ad.objects.count() == 1
        assertRedirects(
            response,
            Ad.objects.get().get_absolute_url(),
            status_code=302,
            target_status_code=200,
        )
        assert "new test offer" in str(response.content)
