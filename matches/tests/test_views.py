import pytest

from django.test import Client

from gifts.models import Listing
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
def listing(owner):
    return Listing.objects.create(title="Old Bicycle", type="offer", owner=owner)


@pytest.fixture
def match(requester, listing):
    m = Match(from_user=requester, message="Interested!")
    m.target = listing
    m.recipient = listing.get_match_owner()
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

    def test_message_notifies_the_other_party_once_while_unread(self, owner, requester, match):
        from notifications.models import Notification

        client = _client_for(requester)
        client.post(match.get_absolute_url(), {"action": "message", "body": "hello"})
        client.post(match.get_absolute_url(), {"action": "message", "body": "hello again"})

        notifications = Notification.objects.filter(tag=Notification.TAG_MESSAGE)
        assert notifications.count() == 1
        assert notifications.get().recipient == owner
        assert not Notification.objects.filter(recipient=requester, tag=Notification.TAG_MESSAGE).exists()

        # once read, the next message notifies again
        notifications.update(is_read=True)
        client.post(match.get_absolute_url(), {"action": "message", "body": "still there?"})
        assert Notification.objects.filter(tag=Notification.TAG_MESSAGE, is_read=False).count() == 1


@pytest.mark.django_db
class TestVolunteeringLists:
    """Community volunteering lists the stays you applied for; volunteer visits
    the ones others applied for at your community."""

    @pytest.fixture
    def stay(self, owner, requester):
        from communities.models import Community
        community = Community.objects.create(name="Hof Lindenblüte", owner=owner)
        m = Match(from_user=requester, message="May I come in May?")
        m.target = community
        m.recipient = community.get_match_owner()
        m.save()
        return m

    def test_volunteer_shows_only_own_applications(self, owner, requester, stay):
        assert list(_client_for(requester).get("/matches/?type=volunteer").context["volunteer_mine"]) == [stay]
        response = _client_for(owner).get("/matches/?type=volunteer")
        assert response.context["volunteer_mine"] == []
        assert "visits" not in response.context

    def test_visits_shows_applications_to_own_community(self, owner, requester, stay):
        response = _client_for(owner).get("/matches/?type=visits")
        assert response.context["visits"] == [stay]
        assert "volunteer_mine" not in response.context
        assert _client_for(requester).get("/matches/?type=visits").context["visits"] == []
