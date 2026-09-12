import pytest

from ..models import Listing


@pytest.mark.django_db
class TestListing:
    def test_creation(self):
        listing = Listing(title="Test", type="offer")
        listing.save()

    def test_short_random_id(self):
        listing = Listing(title="Test", type="offer")
        listing.save()
        assert len(listing.pk) == 8
