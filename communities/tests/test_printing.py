import pytest

from gift_economy.matches.models import Match
from .test_visit_stage import _apply, _client, _url, ambassador, community, ole  # noqa: F401


def _with_answers(membership):
    application = membership.application
    application.answers += [
        {"key": "why_here", "type": "info", "kind": "text", "text": "Why us?", "sensitive": False, "answer": "The orchard."},
        {"key": "support", "type": "info", "kind": "text", "text": "Support?", "sensitive": True, "answer": "My back pain."},
    ]
    application.save(update_fields=["answers"])
    return membership


@pytest.mark.django_db
class TestPrinting:
    def test_the_members_copy_leaves_out_what_only_the_ambassador_sees(self, community, ambassador, ole):
        membership = _with_answers(_apply(ole, community))
        page = _client(ambassador).get(_url("print_application", membership), HTTP_ACCEPT_LANGUAGE="en").content.decode()
        assert "The orchard." in page and "What would make you leave?" in page
        assert "My back pain." not in page
        assert "The answers only the ambassador sees are not included." in page

    def test_the_ambassador_may_print_a_copy_for_themselves(self, community, ambassador, ole):
        membership = _with_answers(_apply(ole, community))
        page = _client(ambassador).get(_url("print_application", membership) + "?sensitive=1", HTTP_ACCEPT_LANGUAGE="en").content.decode()
        assert "My back pain." in page and "It is for the ambassador only" in page

    def test_only_the_ambassador_prints_it(self, community, ambassador, ole):
        membership = _apply(ole, community)
        assert _client(ole).get(_url("print_application", membership)).status_code == 403

    def test_the_button_is_on_the_application_for_the_ambassador(self, community, ambassador, ole):
        membership = _apply(ole, community)
        url = _url("print_application", membership)
        assert url in _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert url not in _client(ole).get(membership.match.get_absolute_url()).content.decode()

    def test_invitations_have_nothing_to_print(self, community, ambassador, ole):
        membership = _apply(ole, community)
        Match.objects.filter(pk=membership.match_id).update(from_user=ambassador, recipient=ole)
        assert _client(ambassador).get(_url("print_application", membership)).status_code == 404
