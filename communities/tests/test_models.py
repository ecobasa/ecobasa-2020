import pytest

from ..models import Community


@pytest.mark.django_db
class TestCommunity:
    def test_creation(self):
        community = Community(name="Test")
        community.save()

    def test_random_slug(self):
        community1 = Community(name="Test")
        community1.save()
        community2 = Community(name="Test")
        community2.save()
        assert len(community1.slug) == 8+1+4
        assert community1.slug != community2.slug
