import pytest

from django.contrib.gis.geos import Point
from django.test import Client

from gift_economy.matches.matching import distance_km

from ..models import User
from ..places import CELL, approximate, town

HOME = Point(13.06213, 52.39887, srid=4326)
ADDRESS = "Lindenweg 7, 14467 Potsdam, Deutschland"


def test_approximate_stays_in_the_cell_and_never_moves():
    shown = approximate(HOME, seed=1)
    assert (shown.x, shown.y) != (HOME.x, HOME.y)
    assert distance_km(shown, HOME) < 2.5
    assert round(shown.x / CELL) == round(HOME.x / CELL) and round(shown.y / CELL) == round(HOME.y / CELL)
    # The same every time, so it can't be averaged out, also from elsewhere in the cell
    assert approximate(HOME, seed=1) == shown
    assert approximate(Point(HOME.x + 0.001, HOME.y, srid=4326), seed=1) == shown
    # Another person in the same cell gets another spot
    assert approximate(HOME, seed=2) != shown


@pytest.mark.parametrize("name, expected", [
    (ADDRESS, "Potsdam, Deutschland"),
    ("Lindenweg, 14467 Potsdam, Deutschland", "Potsdam, Deutschland"),
    ("7 Elm Street, Springfield, United Kingdom", "Springfield, United Kingdom"),
    ("Potsdam, Brandenburg, Deutschland", "Potsdam, Brandenburg, Deutschland"),
    ("Deutschland", "Deutschland"),
    ("", ""),
    (None, None),
])
def test_town_leaves_out_the_street(name, expected):
    assert town(name) == expected


@pytest.mark.django_db
class TestProfile:

    @pytest.fixture
    def person(self):
        return User.objects.create_user(
            email="lina@example.com", password="secret", username="lina", name="Lina",
            location=HOME, location_name=ADDRESS,
        )

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_only_for_members(self, person):
        response = Client().get(person.get_absolute_url())
        assert response.status_code == 302 and response.url.startswith("/users/login/")

    def test_others_see_only_about_where(self, person):
        other = User.objects.create_user(email="ole@example.com", password="secret", username="ole")
        response = self._client_for(other).get(person.get_absolute_url())
        assert response.context["place_name"] == "Potsdam, Deutschland"
        assert response.context["place_point"] == approximate(HOME, person.pk)
        content = response.content.decode()
        assert "Lindenweg" not in content and str(HOME.x) not in content

    def test_they_see_their_own_exactly(self, person):
        context = self._client_for(person).get(person.get_absolute_url()).context
        assert context["place_name"] == ADDRESS and context["place_point"] == HOME
