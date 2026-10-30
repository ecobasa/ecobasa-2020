import pytest

from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse

from gift_economy.matches.models import Match
from projects.models import Project
from users.models import User
from users.places import approximate

from ..models import Community

FARM = Point(11.57512, 48.13743, srid=4326)
ADDRESS = "Wiesenweg 3, 85540 Haar, Deutschland"


def _client_for(user=None):
    client = Client()
    if user:
        client.force_login(user)
    return client


@pytest.fixture
def ambassador():
    return User.objects.create_user(email="amb@example.com", password="secret", username="amb")


@pytest.fixture
def volunteer():
    return User.objects.create_user(email="vol@example.com", password="secret", username="vol")


@pytest.fixture
def community(ambassador):
    return Community.objects.create(
        name="Hof Wiesengrund", owner=ambassador, location=FARM, location_name=ADDRESS, telephone="+49 89 1234567",
    )


def _stay(volunteer, target, status):
    match = Match(from_user=volunteer, recipient=target.get_match_owner(), message="May I come?", status=status)
    match.target = target
    match.save()
    return match


@pytest.mark.django_db
class TestWhoSeesTheCommunitysPlace:
    """Most communities don't want visitors who didn't ask: their exact place, address and
    phone number only for members and those whose stay was accepted, unless public."""

    def test_visitors_see_it_roughly_without_address_and_phone(self, community):
        response = _client_for().get(community.get_absolute_url())
        content = response.content.decode()
        assert response.context["place_point"] == approximate(FARM, community.place_seed)
        assert "Haar, Deutschland" in content
        assert "Wiesenweg" not in content and "1234567" not in content and str(FARM.x) not in content
        assert "Address and phone number are shared once your visit is accepted." in content

    def test_its_ambassador_sees_it_exactly(self, community, ambassador):
        content = _client_for(ambassador).get(community.get_absolute_url()).content.decode()
        assert "Wiesenweg 3" in content and "1234567" in content and str(FARM.x) in content

    @pytest.mark.parametrize("status, sees", [(Match.STATUS_PENDING, False), (Match.STATUS_ACCEPTED, True)])
    def test_a_volunteer_once_their_stay_is_accepted(self, community, volunteer, status, sees):
        _stay(volunteer, community, status)
        assert community.shows_place_to(volunteer) is sees
        assert ("1234567" in _client_for(volunteer).get(community.get_absolute_url()).content.decode()) is sees

    def test_also_after_helping_with_one_of_its_projects(self, community, volunteer):
        _stay(volunteer, Project.objects.create(community=community, title="Straw-bale shed"), Match.STATUS_ACCEPTED)
        assert community.shows_place_to(volunteer)

    def test_everyone_if_its_public(self, community):
        community.location_public = True
        community.save()
        content = _client_for().get(community.get_absolute_url()).content.decode()
        assert "Wiesenweg 3" in content and "1234567" in content and str(FARM.x) in content


@pytest.mark.django_db
class TestTheMap:

    def test_shows_it_in_its_cell(self, community):
        x, y = _client_for().get(reverse("communities:api-markers")).json()["features"][0]["geometry"]["coordinates"]
        shown = approximate(FARM, community.place_seed)
        assert (x, y) == pytest.approx((shown.x, shown.y))

    def test_a_small_map_section_around_it_finds_nothing(self, community):
        bbox = f"{FARM.x - 0.0005},{FARM.y - 0.0005},{FARM.x + 0.0005},{FARM.y + 0.0005}"
        assert _client_for().get(reverse("communities:api-markers"), {"bbox": bbox}).json()["features"] == []

    def test_suggestions_never_name_the_street(self, community):
        names = [s["value"] for s in _client_for().get(reverse("communities:api-suggest"), {"q": "Wiesen"}).json()]
        assert not any("Wiesenweg" in name for name in names)
