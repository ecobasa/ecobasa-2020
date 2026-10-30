import pytest

from django.test import Client


class TestHomepage:
    @pytest.mark.django_db
    def test_get(self, client: Client):
        response = client.get("/")
        assert response.status_code == 200
        assert "ecobasa" in str(response.content)


@pytest.mark.django_db
def test_the_homepage_names_tool_libraries_and_car_sharing(client):
    page = client.get("/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "Tool library: lend instead of buying twice" in page and "Share vehicles: cargo bike, car, trailer or van" in page
