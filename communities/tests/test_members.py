import pytest

from django.test import Client
from django.urls import reverse

from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match
from notifications.models import Notification
from users.models import User
from ..models import Community, Membership


def _user(email, name=""):
    return User.objects.create_user(email=email, password="secret", name=name or email.split("@")[0])


def _client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def ambassador(db):
    return _user("rosa@example.com", "Rosa")


@pytest.fixture
def community(ambassador):
    return Community.objects.create(name="Hof Kleeblatt", ambassador=ambassador)


@pytest.fixture
def ole(db):
    return _user("ole@example.com", "Ole")


def _apply(user, community, message="I live in the green caravan."):
    return _client(user).post(reverse("communities:apply", args=[community.slug]), {"message": message})


def _application(user, community):
    return Membership.objects.get(community=community, user=user).match


@pytest.mark.django_db
class TestMembership:
    def test_ambassador_is_a_member(self, community, ambassador):
        assert community.members() == [ambassador]
        assert ambassador.member_communities() == [community]

    def test_new_ambassador_becomes_a_member(self, community, ambassador, ole):
        community.ambassador = ole
        community.save()
        assert community.members() == [ole, ambassador]
        assert community.memberships.filter(user=ole).count() == 1

    def test_applying_asks_the_ambassador(self, community, ambassador, ole):
        response = _apply(ole, community)
        match = _application(ole, community)
        assert response.status_code == 302 and response.url == match.get_absolute_url()
        assert (match.recipient, match.status, match.message) == (ambassador, Match.STATUS_PENDING, "I live in the green caravan.")
        assert match.target.community == community
        assert Notification.objects.filter(recipient=ambassador, match=match, tag=Notification.TAG_REQUESTED).exists()
        # Not a member until accepted, and not a stay at the community
        assert not community.is_member(ole)
        assert not match.is_community_stay

    def test_applying_twice_keeps_one_application(self, community, ole):
        _apply(ole, community)
        _apply(ole, community)
        assert Membership.objects.filter(community=community, user=ole).count() == 1

    def test_accepted_application_makes_a_member(self, community, ambassador, ole):
        _apply(ole, community)
        match = _application(ole, community)
        _client(ambassador).post(reverse("matches:detail", args=[match.pk]), {"action": "accept"})
        match.refresh_from_db()
        assert match.status == Match.STATUS_ACCEPTED
        assert community.members() == [ambassador, ole]
        assert community in ole.member_communities()

    def test_declined_application_can_be_made_again(self, community, ole):
        _apply(ole, community)
        Match.objects.filter(pk=_application(ole, community).pk).update(status=Match.STATUS_DECLINED)
        assert community.membership_of(ole) is None
        _apply(ole, community)
        assert community.memberships.current().filter(user=ole).count() == 1

    def test_application_shows_in_the_ambassadors_list(self, community, ambassador, ole):
        _apply(ole, community)
        response = _client(ambassador).get(reverse("matches:list") + "?type=members")
        assert response.status_code == 200
        assert list(response.context["page"].object_list) == [_application(ole, community)]

    def test_application_is_not_a_volunteer_visit(self, community, ambassador, ole):
        _apply(ole, community)
        response = _client(ambassador).get(reverse("matches:list") + "?type=volunteer")
        assert list(response.context["page"].object_list) == []


@pytest.mark.django_db
class TestMemberRights:
    @pytest.fixture
    def member(self, community, ole):
        Membership.objects.create(community=community, user=ole)
        return ole

    def test_member_edits_the_community(self, community, member):
        response = _client(member).get(reverse("communities:update", args=[community.slug]))
        assert response.status_code == 200

    def test_stranger_does_not_edit_the_community(self, community):
        stranger = _user("eve@example.com")
        response = _client(stranger).get(reverse("communities:update", args=[community.slug]))
        assert response.status_code == 302

    def test_member_does_not_delete_the_community(self, community, member):
        _client(member).post(reverse("communities:delete", args=[community.slug]))
        assert Community.objects.filter(pk=community.pk).exists()

    def test_member_adds_and_edits_its_listings(self, community, member, ambassador):
        response = _client(member).get(reverse("gifts:create") + f"?community={community.slug}")
        assert response.status_code == 200
        wish = Listing.objects.create(community=community, type=Listing.TYPE_WISH, title="Wheelbarrow")
        assert wish.can_edit(member)
        # Requests about it still go to the ambassador
        assert wish.manager == ambassador

    def test_member_sees_the_exact_place(self, community, member):
        assert community.shows_place_to(member)

    def test_members_are_public(self, client, community, member):
        response = client.get(community.get_absolute_url())
        assert [m.user for m in response.context["member_list"]] == [community.ambassador, member]
        assert "Ole" in response.content.decode()


@pytest.mark.django_db
class TestLeavingAndHandingOver:
    @pytest.fixture
    def membership(self, community, ole):
        return Membership.objects.create(community=community, user=ole)

    def test_member_leaves(self, community, membership, ole):
        _client(ole).post(reverse("communities:leave", args=[community.slug]))
        membership.refresh_from_db()
        assert membership.ended_at is not None
        assert not community.is_member(ole)

    def test_ambassador_does_not_leave(self, community, ambassador):
        _client(ambassador).post(reverse("communities:leave", args=[community.slug]))
        assert community.is_member(ambassador)

    def test_ambassador_removes_a_member(self, community, ambassador, membership, ole):
        _client(ambassador).post(reverse("communities:remove_member", args=[community.slug, membership.pk]))
        assert not community.is_member(ole)

    def test_member_does_not_remove_others(self, community, ambassador, membership, ole):
        own = community.memberships.get(user=ambassador)
        response = _client(ole).post(reverse("communities:remove_member", args=[community.slug, own.pk]))
        assert response.status_code == 403
        assert community.is_member(ambassador)

    def test_hand_over_moves_open_requests(self, community, ambassador, membership, ole):
        guest = _user("guest@example.com")
        stay = Match(from_user=guest, recipient=ambassador, message="Can I come in May?")
        stay.target = community
        stay.save()
        event = Event.objects.create(community=community, title="Harvest")
        help_ = Match(from_user=guest, recipient=ambassador, message="I'll help.")
        help_.target = event
        help_.save()
        declined = Match(from_user=guest, recipient=ambassador, message="Earlier", status=Match.STATUS_DECLINED)
        declined.target = community
        declined.save()

        _client(ambassador).post(reverse("communities:hand_over", args=[community.slug, membership.pk]))
        community.refresh_from_db()
        assert community.ambassador == ole
        assert community.is_member(ambassador)
        assert Match.objects.get(pk=stay.pk).recipient == ole
        assert Match.objects.get(pk=help_.pk).recipient == ole
        assert Match.objects.get(pk=declined.pk).recipient == ambassador
        # The one before can leave now
        _client(ambassador).post(reverse("communities:leave", args=[community.slug]))
        assert not community.is_member(ambassador)


@pytest.mark.django_db
def test_application_cards_show_avatars(community, ambassador, ole):
    _apply(ole, community)
    # Without pictures: the person's and the community's icon in the avatar circle
    received = _client(ambassador).get(reverse("matches:list") + "?type=members").content.decode()
    assert '<i class="fa fa-user">' in received
    sent = _client(ole).get(reverse("matches:list") + "?type=members&box=sent").content.decode()
    assert f'<i class="fa-solid {community.get_type_icon()}">' in sent
