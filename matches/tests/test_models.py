import pytest

from gifting.models import Ad
from users.models import User

from ..models import Match, MatchMessage


@pytest.fixture
def owner():
    return User.objects.create_user(email="owner@example.com", password="secret", username="owner")


@pytest.fixture
def requester():
    return User.objects.create_user(email="requester@example.com", password="secret", username="requester")


@pytest.fixture
def ad(owner):
    return Ad.objects.create(title="Old Bicycle", type="offer", owner=owner)


@pytest.mark.django_db
class TestMatch:
    def test_creation_resolves_generic_target(self, requester, ad):
        match = Match(from_user=requester, message="I'd love this!")
        match.target = ad
        match.recipient = ad.get_match_owner()
        match.save()

        fetched = Match.objects.get(pk=match.pk)
        assert fetched.target == ad
        assert fetched.recipient == ad.owner
        assert fetched.status == Match.STATUS_PENDING

    def test_ad_deletion_cascades_to_match(self, requester, ad):
        match = Match(from_user=requester, message="hi")
        match.target = ad
        match.recipient = ad.get_match_owner()
        match.save()

        ad.delete()

        assert not Match.objects.filter(pk=match.pk).exists()

    def test_resolved_location_your_place_uses_target_location(self, requester, ad, owner):
        owner.location_name = "Berlin"
        owner.save()

        match = Match(from_user=requester, message="hi", location_type=Match.LOC_YOUR_PLACE)
        match.target = ad
        match.recipient = ad.get_match_owner()
        match.save()

        assert "Berlin" in match.resolved_location()

    def test_match_message_thread_ordering(self, requester, ad):
        match = Match(from_user=requester, message="hi")
        match.target = ad
        match.recipient = ad.get_match_owner()
        match.save()

        MatchMessage.objects.create(match=match, sender=requester, body="first")
        MatchMessage.objects.create(match=match, sender=ad.owner, body="second")

        bodies = list(match.thread.values_list("body", flat=True))
        assert bodies == ["first", "second"]
