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


@pytest.mark.django_db
def test_the_homepage_shows_the_next_online_gift_circles_those_in_one_s_language_first(client):
    from datetime import time, timedelta

    from django.utils import timezone

    from events import kinds
    from events.models import Event
    from users.models import User

    host = User.objects.create_user(email="mira@example.com", password="secret", name="Mira")
    today = timezone.localdate()

    def circle(title, days, languages, **fields):
        day = today + timedelta(days=days)
        fields.setdefault("is_online", True)
        return Event.objects.create(
            kind=kinds.GIFT_CIRCLE, title=title, host_user=host, starts_on=day, ends_on=day,
            timezone="Europe/Berlin", languages=languages, **fields,
        )

    circle("Rund um Saatgut", 2, ["de"])
    circle("Seeds and seedlings", 5, ["en", "fr"])
    circle("Over already", 0, ["en"], starts_at=time(0, 0), ends_at=time(0, 15))
    circle("In the park", 1, ["en"], is_online=False)
    page = client.get("/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "Gift-circles you can join from anywhere" in page and "English, French" in page
    assert page.index("Seeds and seedlings") < page.index("Rund um Saatgut")
    assert "Over already" not in page and "In the park" not in page
