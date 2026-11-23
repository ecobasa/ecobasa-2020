import pytest

from django.test import Client


class TestHomepage:
    @pytest.mark.django_db
    def test_get(self, client: Client):
        response = client.get("/")
        assert response.status_code == 200
        assert "ecobasa" in str(response.content)


@pytest.mark.django_db
def test_the_homepage_shows_the_next_online_gift_circles_those_in_one_s_language_first(client):
    from datetime import time, timedelta

    from django.contrib.gis.geos import Point
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
    circle("Around Lyon", 3, ["en"], location_name="Lyon, France", location=Point(4.83, 45.76, srid=4326))
    shown = client.get("/", HTTP_ACCEPT_LANGUAGE="en").context["online_circles"]
    assert [event.title for event in shown] == ["Seeds and seedlings", "Rund um Saatgut"]


@pytest.mark.django_db
def test_the_search_goes_straight_to_the_one_list_with_hits_and_shows_an_overview_for_several(client):
    from django.contrib.gis.geos import Point
    from django.urls import reverse

    from communities.models import Community
    from users.models import User

    Community.objects.create(name="Lindenhof", description="An orchard of old apple varieties")
    Community.objects.create(name="Sonnenwiese", description="Apple juice in autumn")
    pioneer = User.objects.create_user(
        email="jona@example.com", password="secret", name="Jona", about="Grafting apple trees",
        email_confirmed=True, shows_on_map=True, location=Point(9.18, 48.78, srid=4326),
    )

    # The pioneers only for people logged in
    response = client.get(reverse("homepage:search"), {"q": "apple"})
    assert response.status_code == 302
    assert response.url == reverse("communities:list") + "?q=apple"
    client.force_login(pioneer)
    response = client.get(reverse("homepage:search"), {"q": "apple"})
    assert [section["key"] for section in response.context["sections"]] == ["communities", "pioneers"]

    response = client.get(reverse("homepage:search"), {"q": "nothing like it"})
    assert response.status_code == 200
    assert response.context["sections"] == []
