import pytest

from django.test import Client

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
def stranger():
    return User.objects.create_user(email="stranger@example.com", password="secret", username="stranger")


@pytest.fixture
def ad(owner):
    return Ad.objects.create(title="Old Bicycle", type="offer", owner=owner)


@pytest.fixture
def match(requester, ad):
    m = Match(from_user=requester, message="Interested!")
    m.target = ad
    m.recipient = ad.get_match_owner()
    m.save()
    return m


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


@pytest.mark.django_db
class TestMatchDetail:
    def test_stranger_gets_404(self, stranger, match):
        response = _client_for(stranger).get(match.get_absolute_url())
        assert response.status_code == 404

    def test_requester_can_view(self, requester, match):
        response = _client_for(requester).get(match.get_absolute_url())
        assert response.status_code == 200

    def test_owner_accepts(self, owner, match):
        response = _client_for(owner).post(match.get_absolute_url(), {"action": "accept"})
        assert response.status_code == 302

        match.refresh_from_db()
        assert match.status == Match.STATUS_ACCEPTED
        assert match.responded_at is not None
        assert match.thread.filter(status_to=Match.STATUS_ACCEPTED).exists()

    def test_owner_declines(self, owner, match):
        _client_for(owner).post(match.get_absolute_url(), {"action": "decline"})
        match.refresh_from_db()
        assert match.status == Match.STATUS_DECLINED

    def test_requester_cannot_accept_before_counter(self, requester, match):
        """Only the owner can decide on a pending match; an unauthorized action is a no-op."""
        response = _client_for(requester).post(match.get_absolute_url(), {"action": "accept"})
        assert response.status_code == 200
        match.refresh_from_db()
        assert match.status == Match.STATUS_PENDING

    def test_owner_counter_proposes(self, owner, requester, match):
        _client_for(owner).post(match.get_absolute_url(), {
            "action": "counter",
            "counter_location_type": Match.LOC_CUSTOM,
            "counter_location": "Neutral ground",
        })
        match.refresh_from_db()
        assert match.status == Match.STATUS_COUNTER

        counter_msg = match.thread.get(status_to=Match.STATUS_COUNTER)
        assert counter_msg.counter_location == "Neutral ground"

        # after a counter, it's the requester's (not the owner's) turn to decide
        response = _client_for(requester).post(match.get_absolute_url(), {"action": "accept"})
        assert response.status_code == 302
        match.refresh_from_db()
        assert match.status == Match.STATUS_ACCEPTED

    def test_plain_message_does_not_change_status(self, requester, match):
        _client_for(requester).post(match.get_absolute_url(), {"action": "message", "body": "just checking in"})
        match.refresh_from_db()
        assert match.status == Match.STATUS_PENDING
        assert match.thread.filter(body="just checking in").exists()
