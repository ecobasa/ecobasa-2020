import pytest

from ..models import Ad


@pytest.mark.django_db
class TestAd:
    def test_creation(self):
        ad = Ad(title="Test", type="offer")
        ad.save()

    def test_short_random_id(self):
        ad = Ad(title="Test", type="offer")
        ad.save()
        assert len(ad.pk) == 8
