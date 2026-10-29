import pytest

from django.contrib.gis.geos import Point
from django.test import Client

from gift_economy.gifts.models import Listing
from users.models import User
from users.places import approximate

from ..models import Match

HOME = Point(9.99312, 53.55108, srid=4326)
ADDRESS = "Fliederweg 12, 22085 Hamburg, Deutschland"


@pytest.fixture
def giver():
    return User.objects.create_user(
        email="giver@example.com", password="secret", username="giver", location=HOME, location_name=ADDRESS,
    )


@pytest.fixture
def asker():
    return User.objects.create_user(email="asker@example.com", password="secret", username="asker")


@pytest.fixture
def match(giver, asker):
    listing = Listing.objects.create(type="offer", title="Ladder", owner=giver)
    match = Match(from_user=asker, recipient=giver, message="Could I borrow it?", location_type=Match.LOC_YOUR_PLACE)
    match.target = listing
    match.save()
    return match


@pytest.mark.django_db
class TestPlacesInAMatch:
    """Asking never gives anyone an address: until accepted both see each other's place
    only roughly."""

    def test_roughly_until_accepted(self, match, giver, asker):
        assert match.location_is_rough()
        _label, name, point = match.target_location()
        assert name == "Hamburg, Deutschland" and point == approximate(HOME, giver.pk)
        client = Client()
        client.force_login(asker)
        content = client.get(match.get_absolute_url()).content.decode()
        assert "Fliederweg" not in content and str(HOME.x) not in content
        assert "The exact place shows once the match is accepted." in content

    def test_exactly_once_accepted(self, match, asker):
        match.status = Match.STATUS_ACCEPTED
        match.save()
        assert not match.location_is_rough()
        assert match.target_location()[1:] == (ADDRESS, HOME)
        client = Client()
        client.force_login(asker)
        assert "Fliederweg 12" in client.get(match.get_absolute_url()).content.decode()
