from datetime import timedelta

import pytest

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gift_economy.gifts.models import Listing
from gift_economy.references.reference_requests import reference_due_at
from users.models import User

from ..models import Loan, Match, MatchMessage


def _user(name):
    return User.objects.create_user(email=f"{name}@example.com", password="secret", username=name)


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


def _day(days):
    return timezone.localdate() + timedelta(days=days)


@pytest.fixture
def lender():
    return _user("lender")


@pytest.fixture
def borrower():
    return _user("borrower")


@pytest.fixture
def ladder(lender):
    return Listing.objects.create(title="Ladder", type="offer", kind="tool", lend=True, owner=lender)


def _ask(client, listing, starts_on, ends_on):
    return client.post(listing.get_absolute_url(), {
        "message": "May I borrow it?", "location_type": Match.LOC_YOUR_PLACE,
        "borrow_from": starts_on.isoformat(), "borrow_to": ends_on.isoformat(),
    })


def _loan(listing, user, starts_on, ends_on, status=Match.STATUS_ACCEPTED):
    match = Match(from_user=user, message="Borrow", status=status)
    match.target = listing
    match.recipient = listing.manager
    match.save()
    match.contributions.create(listing=listing)
    Loan.objects.create(match=match, starts_on=starts_on, ends_on=ends_on)
    return match


@pytest.mark.django_db
class TestListing:
    def test_only_a_tool_is_lent(self, lender):
        response = _client_for(lender).post(reverse("gifts:create"), {
            "type": "offer", "kind": "material", "title": "Clay", "lend": "on",
        })
        assert response.status_code == 302
        assert not Listing.objects.get(title="Clay").lend

    def test_a_tool_to_lend_says_so(self, ladder):
        assert ladder.kind_label == "Tool to lend"
        ladder.type = Listing.TYPE_WISH
        assert ladder.kind_label == "Tool to borrow"

    def test_lending_it_doesnt_give_it_away(self, ladder, borrower):
        _loan(ladder, borrower, _day(1), _day(3))
        assert ladder.status == Listing.STATUS_OPEN
        assert Listing.objects.open().filter(pk=ladder.pk).exists()

    def test_a_tool_given_away_is_used_up(self, lender, borrower):
        drill = Listing.objects.create(title="Drill", type="offer", kind="tool", owner=lender)
        _loan(drill, borrower, _day(1), _day(3))
        Loan.objects.all().delete()
        assert not Listing.objects.open().filter(pk=drill.pk).exists()

    def test_free_unless_its_loans_overlap(self, ladder, borrower):
        _loan(ladder, borrower, _day(5), _day(7))
        assert ladder.is_free(_day(1), _day(4))
        assert not ladder.is_free(_day(7), _day(9))
        assert ladder.is_free(_day(8), _day(9))

    def test_requested_loans_dont_block(self, ladder, borrower):
        _loan(ladder, borrower, _day(5), _day(7), status=Match.STATUS_PENDING)
        assert ladder.is_free(_day(5), _day(7))

    def test_several_of_it_lend_at_once(self, ladder, borrower):
        ladder.quantity = 2
        ladder.save()
        _loan(ladder, borrower, _day(5), _day(7))
        assert ladder.is_free(_day(6), _day(6))
        _loan(ladder, _user("other"), _day(6), _day(6))
        assert not ladder.is_free(_day(6), _day(6))


@pytest.mark.django_db
class TestAskingToBorrow:
    def test_asking_saves_the_days(self, ladder, borrower):
        response = _ask(_client_for(borrower), ladder, _day(2), _day(4))
        assert response.status_code == 302
        match = Match.objects.get()
        assert match.is_loan
        assert (match.loan.starts_on, match.loan.ends_on) == (_day(2), _day(4))
        assert match.lender == ladder.owner and match.borrower == borrower

    def test_the_days_are_needed(self, ladder, borrower):
        response = _client_for(borrower).post(ladder.get_absolute_url(), {
            "message": "May I?", "location_type": Match.LOC_YOUR_PLACE,
        })
        assert response.status_code == 200
        assert not Match.objects.exists()

    def test_it_comes_back_after_it_is_borrowed(self, ladder, borrower):
        response = _ask(_client_for(borrower), ladder, _day(4), _day(2))
        assert "come back before" in response.content.decode()
        assert not Match.objects.exists()

    def test_not_while_it_is_lent(self, ladder, borrower):
        _loan(ladder, _user("other"), _day(3), _day(5))
        response = _ask(_client_for(borrower), ladder, _day(4), _day(6))
        assert "already lent" in response.content.decode()
        assert Match.objects.count() == 1

    def test_the_tool_shows_when_it_is_lent(self, ladder, borrower):
        _loan(ladder, borrower, _day(3), _day(5))
        response = Client().get(ladder.get_absolute_url())
        assert "Already lent" in response.content.decode()

    def test_a_tool_given_away_asks_no_days(self, lender, borrower):
        drill = Listing.objects.create(title="Drill", type="offer", kind="tool", owner=lender)
        response = _client_for(borrower).post(drill.get_absolute_url(), {
            "message": "Want it", "location_type": Match.LOC_YOUR_PLACE,
        })
        assert response.status_code == 302
        assert not Match.objects.get().is_loan


@pytest.mark.django_db
class TestAgreeing:
    def test_accepting_takes_the_counter_proposed_days(self, ladder, lender, borrower):
        match = _loan(ladder, borrower, _day(2), _day(4), status=Match.STATUS_PENDING)
        _client_for(lender).post(match.get_absolute_url(), {
            "action": "counter", "counter_stay_from": _day(6).isoformat(), "counter_stay_to": _day(8).isoformat(),
            "counter_location_type": Match.LOC_MY_PLACE,
        })
        match.refresh_from_db()
        assert match.status == Match.STATUS_COUNTER
        assert match.loan_period() == (_day(6), _day(8))

        _client_for(borrower).post(match.get_absolute_url(), {"action": "accept"})
        match.refresh_from_db()
        assert match.status == Match.STATUS_ACCEPTED
        assert (match.loan.starts_on, match.loan.ends_on) == (_day(6), _day(8))

    def test_not_accepted_while_it_is_lent(self, ladder, lender, borrower):
        _loan(ladder, _user("other"), _day(3), _day(5))
        match = _loan(ladder, borrower, _day(4), _day(6), status=Match.STATUS_PENDING)
        _client_for(lender).post(match.get_absolute_url(), {"action": "accept"})
        match.refresh_from_db()
        assert match.status == Match.STATUS_PENDING
        assert not MatchMessage.objects.filter(match=match).exists()

    def test_the_reference_is_asked_for_after_it_came_back(self, ladder, borrower, settings):
        match = _loan(ladder, borrower, _day(2), _day(4))
        due = reference_due_at(match)
        assert timezone.localdate(due) == _day(4 + settings.REFERENCE_REQUEST_DELAY_DAYS)


@pytest.mark.django_db
class TestLendingCalendar:
    def test_in_the_dashboard_once_a_tool_is_lent(self, lender, borrower):
        client = _client_for(lender)
        assert reverse("matches:lending") not in client.get(reverse("gifts:mine")).content.decode()
        Listing.objects.create(title="Ladder", type="offer", kind="tool", lend=True, owner=lender)
        assert reverse("matches:lending") in client.get(reverse("gifts:mine")).content.decode()

    def test_in_the_dashboard_of_who_borrows(self, ladder, borrower):
        _loan(ladder, borrower, _day(2), _day(4))
        assert reverse("matches:lending") in _client_for(borrower).get(reverse("gifts:mine")).content.decode()

    def test_shows_whom_it_is_lent_to(self, ladder, lender, borrower):
        borrower.name = "Bea"
        borrower.save()
        starts_on = _day(1)
        _loan(ladder, borrower, starts_on, starts_on + timedelta(days=2))
        response = _client_for(lender).get(reverse("matches:lending"), {"month": starts_on.strftime("%Y-%m")})
        assert response.status_code == 200
        assert [lending.person for lending in response.context["lent_out"]] == [borrower]
        assert "Bea" in response.content.decode()

    def test_shows_what_they_borrow(self, ladder, borrower):
        starts_on = _day(1)
        _loan(ladder, borrower, starts_on, starts_on)
        response = _client_for(borrower).get(reverse("matches:lending"), {"month": starts_on.strftime("%Y-%m")})
        assert [lending.tool for lending in response.context["borrowed"]] == [ladder]
        assert response.context["lent_out"] == []

    def test_requests_for_the_same_days_clash(self, ladder, lender, borrower):
        starts_on = _day(1)
        _loan(ladder, borrower, starts_on, starts_on)
        _loan(ladder, _user("other"), starts_on, starts_on, status=Match.STATUS_PENDING)
        response = _client_for(lender).get(reverse("matches:lending"), {"month": starts_on.strftime("%Y-%m")})
        assert [day.date for day in response.context["clash_days"]] == [starts_on]

    def test_where_the_tool_is_today(self, ladder, lender, borrower):
        _loan(ladder, borrower, _day(0), _day(2))
        response = _client_for(lender).get(reverse("matches:lending"))
        [tool] = response.context["tools"]
        assert [lending.person for lending in tool.lent_now] == [borrower]

    def test_only_their_own(self, ladder, borrower):
        _loan(ladder, borrower, _day(1), _day(1))
        response = _client_for(_user("stranger")).get(reverse("matches:lending"))
        assert response.context["lent_out"] == [] and response.context["borrowed"] == []


@pytest.mark.django_db
def test_the_pages_show_the_days(ladder, lender, borrower):
    form = _client_for(borrower).get(ladder.get_absolute_url()).content.decode()
    assert 'name="borrow_from"' in form and 'name="proposed_date"' not in form
    match = _loan(ladder, borrower, _day(2), _day(4), status=Match.STATUS_PENDING)
    page = _client_for(lender).get(match.get_absolute_url()).content.decode()
    assert "Asked to borrow" in page
    assert 'name="counter_stay_from"' in page and 'name="counter_date"' not in page
