import pytest

from django.test import Client
from django.urls import reverse
from django.utils import translation

from gift_economy.matches.emails import make_action_token
from gift_economy.matches.models import Match, MatchMessage
from notifications.models import Notification
from .. import declines
from ..models import Membership
from .test_visit_stage import _accept, _apply, _client, ambassador, community, ole  # noqa: F401


def _decline(user, membership, body, decline_as=declines.NO):
    response = _client(user).post(membership.match.get_absolute_url(), {
        "action": "decline", "body": body, "decline_as": decline_as,
    })
    membership.refresh_from_db()
    membership.match.refresh_from_db()
    return response


@pytest.mark.django_db
class TestDeclining:
    def test_texts_for_the_stage_it_is_at(self, community, ole):
        membership = _apply(ole, community)
        with translation.override("en"):
            texts = {kind: text for kind, label, text in membership.decline_texts()}
            assert "Hello Ole," in texts[declines.NO] and "Hof Kleeblatt" in texts[declines.NO]
            assert "not to invite you for a visit" in texts[declines.NO]
            assert texts[declines.NO].endswith("Rosa")
            membership.stage = Membership.STAGE_VISIT
            visit_texts = {kind: text for kind, label, text in membership.decline_texts()}
            assert "After your visit" in visit_texts[declines.NOT_NOW]
        assert all(declines.is_unfilled(text) for text in texts.values())

    def test_the_part_in_brackets_must_be_filled_in_or_deleted(self, community, ambassador, ole):
        membership = _apply(ole, community)
        with translation.override("en"):
            text = dict((kind, text) for kind, label, text in membership.decline_texts())[declines.NOT_NOW]
        response = _decline(ambassador, membership, text, declines.NOT_NOW)
        assert membership.match.status == Match.STATUS_PENDING
        assert "decline=1" in response["Location"]

        _decline(ambassador, membership, declines.UNFILLED.sub("we have no free room this year", text), declines.NOT_NOW)
        assert membership.match.status == Match.STATUS_DECLINED
        assert membership.declined_as == declines.NOT_NOW

    def test_a_message_isnt_required(self, community, ambassador, ole):
        membership = _apply(ole, community)
        _decline(ambassador, membership, "")
        assert membership.match.status == Match.STATUS_DECLINED and membership.declined_as == declines.NO

    def test_after_the_visit(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        _decline(ambassador, membership, "Thank you for the days with us.")
        assert membership.match.status == Match.STATUS_DECLINED and not membership.is_visiting

    def test_the_applicant_sees_no_red_declined(self, community, ambassador, ole):
        membership = _apply(ole, community)
        _decline(ambassador, membership, "Thank you.", declines.NOT_NOW)
        with translation.override("en"):
            page = _client(ole).get(membership.match.get_absolute_url()).content.decode()
            notification = Notification.objects.get(recipient=ole, tag=Notification.TAG_DECLINED)
            assert notification.text == "Rosa answered your membership application: Hof Kleeblatt"
        assert "Not now" in page and "pill bg-red" not in page and "border-red" not in page
        assert reverse("communities:list") + "?looking=1" in page
        assert not notification.is_red

    def test_changing_it_back_forgets_the_no(self, community, ambassador, ole):
        membership = _apply(ole, community)
        _decline(ambassador, membership, "Thank you.", declines.NOT_NOW)
        membership = _accept(ambassador, membership, Membership.STAGE_VISIT)
        assert membership.is_visiting and membership.declined_as == ""

    def test_the_email_link_doesnt_decline(self, community, ole):
        membership = _apply(ole, community)
        response = Client().get(reverse("matches:email_action", args=[make_action_token(membership.match.pk, "decline")]))
        membership.match.refresh_from_db()
        assert membership.match.status == Match.STATUS_PENDING
        assert "decline=1" in response["Location"]

    def test_the_ambassador_gets_the_texts(self, community, ambassador, ole):
        membership = _apply(ole, community)
        with translation.override("en"):
            page = _client(ambassador).get(membership.match.get_absolute_url() + "?decline=1").content.decode()
        assert "Start from a text" in page and "Saying no with care" in page

    def test_invitations_decline_as_before(self, community, ambassador, ole):
        match = Match(from_user=ambassador, recipient=ole, location_type="")
        membership = Membership.objects.create(community=community, user=ole, stage=Membership.STAGE_APPLICATION)
        match.target = membership
        match.save()
        membership.match = match
        membership.save(update_fields=["match"])
        _client(ole).post(match.get_absolute_url(), {"action": "decline", "body": "[sorry]"})
        match.refresh_from_db()
        assert match.status == Match.STATUS_DECLINED and match.gentle_decline is None
        assert MatchMessage.objects.filter(match=match, status_to=Match.STATUS_DECLINED).exists()
