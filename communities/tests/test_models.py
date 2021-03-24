import pytest

from ..models import Community


@pytest.mark.django_db
class TestCommunity:
    def test_creation(self):
        community = Community(name="Test")
        community.save()

    def test_unique_slug(self):
        community1 = Community(name="Test")
        community1.save()
        community2 = Community(name="Test")
        community2.save()
        community3 = Community(name="Test")
        community3.save()
        assert community1.slug == "test"
        assert community2.slug == "test-2"
        assert community3.slug == "test-3"
