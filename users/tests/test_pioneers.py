import pytest

from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse

from ..models import User
from ..places import approximate

HOME = Point(13.06213, 52.39887, srid=4326)


def _person(email, **fields):
    return User.objects.create_user(email=email, password="x", name=email.split("@")[0], location=HOME, **fields)


@pytest.mark.django_db
def test_the_map_shows_only_who_shows_themselves_about_where_they_live():
    viewer = _person("viewer@example.org")
    shown = _person("mila@example.org")
    _person("hidden@example.org", shows_on_map=False)
    _person("unconfirmed@example.org", email_confirmed=False)
    User.objects.create_user(email="nowhere@example.org", password="x", name="nowhere")
    client = Client()
    client.force_login(viewer)
    features = client.get(reverse("pioneers:api-markers")).json()["features"]
    by_name = {feature["properties"]["name"]: feature for feature in features}
    assert set(by_name) == {"viewer", "mila"}
    rough = approximate(HOME, shown.pk)
    assert by_name["mila"]["geometry"]["coordinates"] == [rough.x, rough.y] != [HOME.x, HOME.y]


@pytest.mark.django_db
def test_visitors_see_no_pioneers():
    _person("mila@example.org")
    response = Client().get(reverse("pioneers:api-markers"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_invite_links_go_back_only_to_this_site():
    viewer = _person("viewer@example.org")
    mila = _person("mila@example.org")
    client = Client()
    client.force_login(viewer)
    url = reverse("pioneers:api-markers")

    def invite(page):
        features = client.get(url, {"invite": page}).json()["features"]
        return next(f["properties"]["invite"] for f in features if f["properties"]["name"] == "mila")

    assert invite("/gift-circles/potluck/invite/?user=3") == f"/gift-circles/potluck/invite/?user=3&user={mila.pk}"
    assert invite("//elsewhere.example/") == ""
    assert invite("https://elsewhere.example/") == ""
