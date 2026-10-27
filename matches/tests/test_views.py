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
class TestVolunteerVisits:
    """One Volunteer Visits page: stays others asked for at your community are
    received, the ones you asked for are sent."""

    @pytest.fixture
    def stay(self, owner, requester):
        from communities.models import Community
        community = Community.objects.create(name="Hof Lindenblüte", owner=owner)
        m = Match(from_user=requester, message="May I come in May?")
        m.target = community
        m.recipient = community.get_match_owner()
        m.save()
        return m

    def test_ambassador_sees_it_as_received(self, owner, stay):
        context = _client_for(owner).get("/matches/?type=volunteer").context
        assert list(context["page"]) == [stay]
        assert [(str(t.label), t.count, t.waiting, t.active) for t in context["tabs"]] == [
            ("Requests to you", 1, 1, True), ("Your requests", 0, 0, False),
        ]

    def test_volunteer_sees_it_as_sent(self, requester, stay):
        response = _client_for(requester).get("/matches/?type=volunteer")
        assert list(response.context["page"]) == [stay]
        assert [t.active for t in response.context["tabs"]] == [False, True]
        assert "Volunteer Visits" in response.content.decode()


@pytest.mark.django_db
class TestMatchLists:
    """One page for gifts and skills: suggestions first, then received and sent as tabs,
    filtered by type and status, paged."""

    def test_open_ones_first_then_the_rest_by_status(self, owner, match, listing, requester):
        done = Match(from_user=requester, message="Earlier", recipient=owner, status=Match.STATUS_DECLINED)
        done.target = listing
        done.save()
        client = _client_for(owner)

        context = client.get("/matches/?type=gift&box=received").context
        assert list(context["page"]) == [match]
        assert [(f.count, f.active) for f in context["filters"]] == [(1, True), (0, False), (1, False), (2, False)]

        assert list(client.get("/matches/?type=gift&box=received&status=declined").context["page"]) == [done]
        assert len(client.get("/matches/?type=gift&box=received&status=all").context["page"].object_list) == 2
        # Gift requests aren't under skills, but under all
        assert not client.get("/matches/?type=skills&box=received&status=all").context["page"].object_list
        assert len(client.get("/matches/?box=received&status=all").context["page"].object_list) == 2

    def test_long_lists_are_paged(self, owner, requester, listing):
        from dashboard_lists import PER_PAGE
        for i in range(PER_PAGE + 3):
            m = Match(from_user=requester, message=f"#{i}", recipient=owner)
            m.target = listing
            m.save()
        page = _client_for(owner).get("/matches/?type=gift&box=received").context["page"]
        assert len(page.object_list) == PER_PAGE
        assert page.paginator.count == PER_PAGE + 3
        assert "page=2" in page.older_url and "type=gift" in page.older_url

    def test_the_page_opens_on_the_suggestions(self, owner, match):
        context = _client_for(owner).get("/matches/").context
        assert [(str(t.label), t.active) for t in context["tabs"]] == [
            ("Suggestions", True), ("Requests to you", False), ("Your requests", False),
        ]
        assert [(str(t.label), t.active) for t in context["types"]] == [("All", True), ("Gifts", False), ("Skills", False)]
        # The request waiting for an answer is counted on its tab
        assert next(t for t in context["tabs"] if str(t.label) == "Requests to you").waiting == 1


@pytest.fixture
def stay(requester, owner):
    """A volunteer stay request at a community."""
    from datetime import datetime

    from django.utils import timezone

    from communities.models import Community

    from ..models import VolunteerDetails

    community = Community.objects.create(name="Green Valley", owner=owner)
    m = Match(from_user=requester, message="Can I come help?")
    m.target = community
    m.recipient = community.get_match_owner()
    m.save()
    VolunteerDetails.objects.create(
        match=m,
        stay_from=timezone.make_aware(datetime(2027, 5, 1)),
        stay_to=timezone.make_aware(datetime(2027, 5, 14)),
    )
    return m


@pytest.mark.django_db
class TestCommunityStayCounter:
    """A stay happens at the community, so the owner can only suggest other dates."""

    def test_owner_sees_only_the_date_option(self, owner, stay):
        content = _client_for(owner).get(stay.get_absolute_url()).content.decode()
        assert 'name="counter_stay_from"' in content
        assert 'value="2027-05-01"' in content
        assert 'name="counter_location_type"' not in content
        assert "counter-pick-map" not in content

    def test_gifts_keep_the_location_option(self, owner, match):
        content = _client_for(owner).get(match.get_absolute_url()).content.decode()
        assert 'name="counter_location_type"' in content
        assert 'name="counter_stay_from"' not in content

    def test_owner_suggests_other_dates(self, owner, requester, stay, mailoutbox):
        from django.utils import timezone

        _client_for(owner).post(stay.get_absolute_url(), {
            "action": "counter",
            "counter_stay_from": "2027-06-01",
            "counter_stay_to": "2027-06-10",
            # a crafted location is ignored for stays
            "counter_location_type": Match.LOC_CUSTOM,
            "counter_location": "Elsewhere",
        })
        stay.refresh_from_db()
        assert stay.status == Match.STATUS_COUNTER

        counter_msg = stay.thread.get(status_to=Match.STATUS_COUNTER)
        assert timezone.localdate(counter_msg.counter_stay_from).isoformat() == "2027-06-01"
        assert timezone.localdate(counter_msg.counter_stay_to).isoformat() == "2027-06-10"
        assert counter_msg.counter_location == ""
        assert counter_msg.counter_location_type == ""

        notification = requester.notifications.get()
        assert "other dates for your stay at" in notification.text
        assert "place" not in notification.text
        assert "01 Jun 2027" in mailoutbox[0].body

        content = _client_for(requester).get(stay.get_absolute_url()).content.decode()
        assert "Suggested stay" in content
        assert "01 Jun 2027&ndash;10 Jun 2027" in content

        # the requester can then accept the new dates
        _client_for(requester).post(stay.get_absolute_url(), {"action": "accept"})
        stay.refresh_from_db()
        assert stay.status == Match.STATUS_ACCEPTED
        content = _client_for(requester).get(stay.get_absolute_url()).content.decode()
        assert "01 Jun 2027&ndash;10 Jun 2027" in content

    def test_counter_needs_a_date(self, owner, stay):
        _client_for(owner).post(stay.get_absolute_url(), {"action": "counter", "body": "Hmm"})
        stay.refresh_from_db()
        assert stay.status == Match.STATUS_PENDING
        assert not stay.thread.exists()

    def test_stay_cannot_end_before_it_starts(self, owner, stay):
        _client_for(owner).post(stay.get_absolute_url(), {
            "action": "counter", "counter_stay_from": "2027-06-10", "counter_stay_to": "2027-06-01",
        })
        stay.refresh_from_db()
        assert stay.status == Match.STATUS_PENDING
