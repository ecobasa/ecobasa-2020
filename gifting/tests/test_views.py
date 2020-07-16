import pytest

from django.test import Client
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects

from users.models import User
from ..models import Ad


@pytest.fixture
def user():
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.fixture
def ads(user):
    return [
        Ad.objects.create(
            title="Test", type="offer", description="testdesc", owner=user
        ),
        Ad.objects.create(
            title="Foobar", type="wish", description="foobardesc", owner=user
        ),
    ]


@pytest.fixture
def ad(user):
    return Ad.objects.create(type="offer", title="test", owner=user)


@pytest.fixture
def user_client(db, user):
    """Return a client logged in as user"""
    client = Client()
    client.login(username=user.email, password="secret")
    return client


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
        response = client.get(f"/gifting/{ad.pk}/")
        assert response.status_code == 200
        assert "test" in str(response.content)


@pytest.mark.django_db
class TestCreate:
    def test_get(self, user_client: Client):
        response = user_client.get("/gifting/create/")
        assert response.status_code == 200

    def test_get_unauth(self, client: Client):
        response = client.get("/gifting/create/", follow=True)
        assertRedirects(
            response,
            "/users/login/?next=/gifting/create/",
            status_code=302,
            target_status_code=200,
        )

    def test_post_invalid(self, user_client: Client):
        response = user_client.post("/gifting/create/")
        assert response.status_code == 200
        assert "This field is required." in str(response.content)

    def test_post_valid(self, user_client: Client, user: User):
        response = user_client.post(
            "/gifting/create/",
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
        ad = Ad.objects.get()
        assert ad.owner == user
        assert "new test offer" in str(response.content)


@pytest.mark.django_db
class TestEdit:
    def test_get(self, user_client: Client, ad: Ad):
        response = user_client.get(f"/gifting/{ad.pk}/edit/")
        assert response.status_code == 200

    def test_get_unauth(self, client: Client, ad: Ad):
        response = client.get(f"/gifting/{ad.pk}/edit/", follow=True)
        assertRedirects(
            response,
            f"/users/login/?next=/gifting/{ad.pk}/edit/",
            status_code=302,
            target_status_code=200,
        )

    def test_404(self, user_client: Client, ad: Ad):
        response = user_client.get("/gifting/abcdefgh/edit/")
        assert response.status_code == 404

    def test_post_invalid(self, user_client: Client, ad: Ad):
        response = user_client.post(f"/gifting/{ad.pk}/edit/")
        assert response.status_code == 200
        assert "This field is required." in str(response.content)

    def test_post_valid(self, user_client: Client, ad: Ad):
        assert Ad.objects.count() == 1
        response = user_client.post(
            f"/gifting/{ad.pk}/edit/",
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


@pytest.mark.django_db
class TestDelete:
    def test_404(self, user_client: Client):
        response = user_client.get("/gifting/abcdefgh/delete/")
        assert response.status_code == 404

    def test_get_unauth(self, client: Client, ad: Ad):
        response = client.get(f"/gifting/{ad.pk}/delete/", follow=True)
        assertRedirects(
            response,
            f"/users/login/?next=/gifting/{ad.pk}/delete/",
            status_code=302,
            target_status_code=200,
        )

    def test_get(self, user_client: Client, ad: Ad):
        response = user_client.get(f"/gifting/{ad.pk}/delete/")
        assert response.status_code == 200

    def test_post(self, user_client: Client, ad: Ad):
        response = user_client.post(f"/gifting/{ad.pk}/delete/", follow=True)
        assertRedirects(
            response,
            reverse("gifting:search"),
            status_code=302,
            target_status_code=200,
        )
        assert Ad.objects.all().exists() == False
        # assert "deleted" in str(response.content)
