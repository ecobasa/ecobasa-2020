import pytest

from gift_economy.matches.models import Match, MatchMessage
from notifications.models import Notification
from .. import declines
from ..models import Family, Membership, MembershipApplication, PastApplication
from .test_declining import _decline
from .test_visit_stage import _accept, _apply, _client, _url, _user, ambassador, community, ole  # noqa: F401


def _delete(user, membership):
    return _client(user).post(_url("delete_application", membership))


@pytest.mark.django_db
class TestDeleting:
    def test_the_applicant_deletes_answers_and_conversation(self, community, ambassador, ole):
        membership = _apply(ole, community)
        match = membership.match
        MatchMessage.objects.create(match=match, sender=ole, body="About my back pain …")
        family = Family.objects.create(community=community, children=[4])
        membership.application.family = family
        membership.application.save(update_fields=["family"])

        response = _delete(ole, membership)
        assert response["Location"] == community.get_absolute_url()
        assert not Membership.objects.filter(pk=membership.pk).exists()
        assert not MembershipApplication.objects.exists()
        assert not Match.objects.filter(pk=match.pk).exists()
        assert not MatchMessage.objects.filter(match_id=match.pk).exists()
        assert not Notification.objects.filter(match_id=match.pk).exists()
        assert not Family.objects.exists()
        past = PastApplication.objects.get()
        assert (past.user, past.community, past.outcome) == (ole, community, PastApplication.APPLIED)

    def test_the_family_stays_while_others_apply_in_it(self, community, ole):
        membership, other = _apply(ole, community), _apply(_user("mia@example.com"), community)
        family = Family.objects.create(community=community)
        for each in (membership, other):
            each.application.family = family
            each.application.save(update_fields=["family"])
        membership.delete_application()
        assert family.applications.get() == other.application

    def test_the_ambassador_deletes_a_declined_one(self, community, ambassador, ole):
        membership = _apply(ole, community)
        _decline(ambassador, membership, "", declines.NOT_NOW)
        response = _delete(ambassador, membership)
        assert "type=members" in response["Location"]
        assert PastApplication.objects.get().outcome == declines.NOT_NOW

    def test_a_member_stays_a_member(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_MEMBER)
        _delete(ole, membership)
        membership.refresh_from_db()
        assert membership.match_id is None and community.is_member(ole)
        assert PastApplication.objects.get().outcome == PastApplication.ACCEPTED

    def test_an_application_in_the_visit_stage_was_accepted(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        _delete(ambassador, membership)
        assert not Membership.objects.filter(pk=membership.pk).exists()
        assert PastApplication.objects.get().outcome == PastApplication.ACCEPTED

    def test_nobody_else_may_delete_it(self, community, ole):
        membership = _apply(ole, community)
        assert _delete(_user("mia@example.com"), membership).status_code == 403
        assert MembershipApplication.objects.exists()

    def test_not_an_invitation(self, community, ambassador, ole):
        membership = Membership.objects.create(community=community, user=ole, stage=Membership.STAGE_APPLICATION)
        match = Match(from_user=ambassador, recipient=ole, location_type="")
        match.target = membership
        match.save()
        membership.match = match
        membership.save(update_fields=["match"])
        assert _delete(ole, membership).status_code == 403

    def test_the_ambassador_sees_how_earlier_ones_ended(self, community, ambassador, ole):
        first = _apply(ole, community)
        _decline(ambassador, first, "")
        second = _apply(ole, community)
        _delete(ole, second)
        third = _apply(ole, community)
        assert [past["outcome"] for past in third.before()] == [PastApplication.APPLIED, declines.NO]


@pytest.mark.django_db
def test_delete_also_ends_the_answer_form(community, ambassador, ole):
    membership = _apply(ole, community)
    action = f'formaction="{_url("delete_application", membership)}"'
    assert action in _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
    assert action in _client(ole).get(membership.match.get_absolute_url()).content.decode()
