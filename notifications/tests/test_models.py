import pytest

from django.utils import translation

from communities.models import Community
from gifts.models import Listing
from matches.emails import notify_match_created, notify_match_response
from matches.models import Match
from users.models import User

from ..models import Notification


@pytest.fixture
def owner():
    return User.objects.create_user(email="owner@example.com", password="secret", username="owner", name="Olga")


@pytest.fixture
def requester():
    return User.objects.create_user(email="requester@example.com", password="secret", username="requester", name="Rafa")


def _match(requester, target):
    m = Match(from_user=requester, message="Interested!", recipient=target.get_match_owner())
    m.target = target
    m.save()
    return m


@pytest.mark.django_db
class TestNotificationText:
    def test_text_follows_the_readers_language(self, owner, requester):
        listing = Listing.objects.create(title="Old Bicycle", type="offer", owner=owner)
        with translation.override("fr"):
            # created while the requester browses in French…
            notify_match_created(_match(requester, listing))
        notification = Notification.objects.get(recipient=owner)

        # …but shown in whatever language the owner reads it in
        with translation.override("de"):
            assert notification.text == "Rafa interessiert sich für dein Angebot: Old Bicycle"
        with translation.override("en"):
            assert notification.text == "Rafa is interested in your offer: Old Bicycle"

    def test_requester_answering_a_counter_proposal(self, owner, requester):
        listing = Listing.objects.create(title="Old Bicycle", type="offer", owner=owner)
        match = _match(requester, listing)
        match.status = Match.STATUS_ACCEPTED
        notify_match_response(match, actor=requester)

        notification = Notification.objects.get(recipient=owner, tag=Notification.TAG_ACCEPTED)
        assert notification.text == "Rafa accepted your counter-proposal for: Old Bicycle"

    def test_falls_back_to_stored_text_without_a_match(self, owner):
        notification = Notification.objects.create(recipient=owner, verb="Welcome!", tag="")
        assert notification.text == "Welcome!"


@pytest.mark.django_db
class TestNotificationIcon:
    @pytest.mark.parametrize("listing_type, icon", [("offer", "fa-gift"), ("wish", "fa-hand-holding-heart")])
    def test_gift_requests(self, owner, requester, listing_type, icon):
        listing = Listing.objects.create(title="Old Bicycle", type=listing_type, owner=owner)
        notify_match_created(_match(requester, listing))
        assert Notification.objects.get(recipient=owner).icon == icon

    def test_volunteer_request(self, owner, requester):
        community = Community.objects.create(name="Goat Farm", owner=owner)
        notify_match_created(_match(requester, community))
        assert Notification.objects.get(recipient=owner).icon == "fa-campground"
