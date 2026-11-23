import pytest

from datetime import timedelta

from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import timezone, translation

from gift_economy.matches.models import Match, create_stay
from notifications.models import Notification
from users.models import User
from ..models import Community, Membership, MembershipApplication


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
    return Community.objects.create(
        name="Hof Kleeblatt", ambassador=ambassador, location=Point(14.98, 51.16), looking_for_members=True,
        after_visit="Six months trial, then the plenum decides.",
    )


@pytest.fixture
def ole(db):
    return _user("ole@example.com", "Ole")


def _apply(user, community, talks=("What would make you leave?",)):
    """An application with answers, as the apply page makes it."""
    membership = Membership.objects.create(community=community, user=user, stage=Membership.STAGE_APPLICATION)
    match = Match(from_user=user, recipient=community.ambassador, message="Hello!", location_type="")
    match.target = membership
    match.save()
    membership.match = match
    membership.save(update_fields=["match"])
    MembershipApplication.objects.create(membership=membership, consented_at=timezone.now(), answers=[
        {"key": "", "type": "discussion", "kind": "text", "text": text, "sensitive": False, "answer": None} for text in talks
    ])
    return membership


def _url(name, membership):
    return reverse(f"communities:{name}", args=[membership.community.slug, membership.pk])


def _days(membership):
    return tuple(timezone.localdate(day).isoformat() for day in membership.suggested_visit())


def _accept(ambassador, membership, accept_as=""):
    _client(ambassador).post(membership.match.get_absolute_url(), {"action": "accept", "accept_as": accept_as})
    membership.refresh_from_db()
    return membership


@pytest.mark.django_db
class TestAccepting:
    def test_the_ambassador_chooses_visit_or_member(self, community, ambassador, ole):
        membership = _apply(ole, community)
        with translation.override("en"):
            page = _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert "Invite to visit" in page and "Make member" in page

        _accept(ambassador, membership, Membership.STAGE_VISIT)
        assert membership.stage == Membership.STAGE_VISIT and membership.is_visiting
        assert not community.is_member(ole) and ole not in community.members()

    def test_making_a_member_right_away(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_MEMBER)
        assert community.is_member(ole) and membership.visit is None

    def test_the_email_link_leads_to_the_answers(self, community, ole):
        from gift_economy.matches.emails import make_action_token

        membership = _apply(ole, community)
        response = Client().get(reverse("matches:email_action", args=[make_action_token(membership.match.pk, "accept")]))
        membership.refresh_from_db()
        assert membership.stage == Membership.STAGE_APPLICATION and membership.match.status == Match.STATUS_PENDING
        assert response["Location"] == membership.match.get_absolute_url() + "#compose"

    def test_the_ambassador_is_asked_to_read_it(self, community, ambassador, ole):
        from django.core import mail
        from django.test import RequestFactory
        from gift_economy.matches.emails import notify_match_created

        membership = _apply(ole, community)
        notify_match_created(membership.match, http_request=RequestFactory().get("/"))
        email = mail.outbox[-1]
        assert email.to == [ambassador.email]
        assert "/matches/action/" not in email.body

    def test_the_emails_keep_what_was_written(self, community, ambassador, ole):
        from django.core import mail

        membership = _apply(ole, community)
        _client(ambassador).post(membership.match.get_absolute_url(), {"action": "message", "body": "Ole's caravan & ours"})
        assert "Ole's caravan & ours" in mail.outbox[-1].body

    def test_who_lives_there_and_invitations_become_members(self, community, ambassador, ole):
        _client(ole).post(reverse("communities:apply", args=[community.slug]), {"message": "The green caravan.", "lives_here": "on"})
        membership = community.memberships.get(user=ole)
        assert membership.stage == Membership.STAGE_APPLICATION
        with translation.override("en"):
            assert "Invite to visit" not in _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert _accept(ambassador, membership).is_counted

        jo = _user("jo@example.com", "Jo")
        _client(ambassador).post(reverse("communities:invite", args=[community.slug]), {"user": jo.pk, "message": "Join us!"})
        invitation = community.memberships.get(user=jo)
        _client(jo).post(invitation.match.get_absolute_url(), {"action": "accept"})
        assert community.is_member(jo)

    def test_existing_members_stay_counted(self, community, ambassador):
        assert community.members() == [ambassador]


@pytest.mark.django_db
class TestTheVisit:
    def test_the_ambassador_suggests_the_first_visit_days(self, community, ambassador, ole):
        membership = _apply(ole, community)
        _accept(ambassador, membership, Membership.STAGE_VISIT)
        # Without days yet, not the applicant
        assert _client(ole).post(_url("visit_days", membership), {"visit_from": "2027-05-03"}).status_code == 403

    def test_days_are_agreed_in_the_conversation(self, community, ambassador, ole):
        membership = _apply(ole, community)
        _client(ambassador).post(membership.match.get_absolute_url(), {
            "action": "accept", "accept_as": Membership.STAGE_VISIT, "body": "Come and see!",
            "visit_from": "2027-05-03", "visit_to": "2027-05-17",
        })
        membership = Membership.objects.get(pk=membership.pk)
        assert _days(membership) == ("2027-05-03", "2027-05-17")
        with translation.override("en"):
            page = _client(ole).get(membership.match.get_absolute_url()).content.decode()
            assert page.index("Come and see!") < page.index("Suggested stay") < page.index("Accept these days")
            # Who proposed waits for the other side
            assert "Accept these days" not in _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert _client(ambassador).post(_url("accept_visit_days", membership)).status_code == 403

        # The applicant proposes other days: a new message, the ambassador is told
        _client(ole).post(_url("visit_days", membership), {"visit_from": "2027-06-01", "visit_to": "2027-06-14", "body": "June is better."})
        membership = Membership.objects.get(pk=membership.pk)
        assert _days(membership) == ("2027-06-01", "2027-06-14")
        assert Notification.objects.filter(recipient=ambassador, match=membership.match).exists()
        with translation.override("en"):
            page = _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert page.count("Accept these days") == 1
        # In the message: the words, the days, then the buttons
        assert page.index("June is better.") < page.rindex("Suggested stay") < page.index("Accept these days") < page.rindex("Suggest other days")

        # The ambassador accepts: the visit is an accepted stay on those days
        _client(ambassador).post(_url("accept_visit_days", membership))
        membership = Membership.objects.get(pk=membership.pk)
        stay = membership.visit
        assert membership.visit_agreed() and stay.status == Match.STATUS_ACCEPTED and stay.from_user == ole
        assert stay.is_community_stay and timezone.localdate(stay.stay_details.stay_from).isoformat() == "2027-06-01"
        assert community.shows_place_to(ole)
        # The agreed days stand in the latest message, of both conversations
        last = membership.match.thread.last()
        assert (last.sender, last.status_to) == (ambassador, Match.STATUS_ACCEPTED)
        assert timezone.localdate(last.counter_stay_from).isoformat() == "2027-06-01"
        assert stay.thread.last().status_to == Match.STATUS_ACCEPTED
        with translation.override("en"):
            page = _client(ole).get(membership.match.get_absolute_url()).content.decode()
        assert page.rindex("Agreed stay") > page.rindex("June is better.") and "Accept these days" not in page

        # Changing them again moves the same stay once accepted
        _client(ambassador).post(_url("visit_days", membership), {"visit_from": "2027-06-08", "visit_to": "2027-06-20"})
        membership = Membership.objects.get(pk=membership.pk)
        assert not membership.visit_agreed()
        _client(ole).post(_url("accept_visit_days", membership))
        membership = Membership.objects.get(pk=membership.pk)
        assert membership.visit == stay and membership.visit_agreed()
        stay.stay_details.refresh_from_db()
        assert timezone.localdate(stay.stay_details.stay_from).isoformat() == "2027-06-08"

        # While invited to visit, the stay is talked over here: its page leads here, the
        # lists leave it out
        for viewer in (ole, ambassador):
            response = _client(viewer).get(stay.get_absolute_url())
            assert response.status_code == 302 and response.url.startswith(membership.match.get_absolute_url())
        response = _client(ambassador).get(reverse("matches:list") + "?type=volunteer")
        assert stay not in list(response.context["page"].object_list)
        # Once a member, the stay is an ordinary one again, with the topics
        membership.make_member()
        with translation.override("en"):
            page = _client(ambassador).get(stay.get_absolute_url()).content.decode()
        assert "What would make you leave?" in page and "Agreed stay" in page

    def test_a_volunteer_request_is_a_proposal_in_the_application(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        _client(ambassador).post(_url("visit_days", membership), {"visit_from": "2027-05-03", "visit_to": "2027-05-17"})
        _client(ole).post(reverse("communities:volunteer_request", args=[community.slug]), {
            "volunteer_mode": "offer", "body": "Two weeks in June?", "stay_from": "2027-06-01T10:00", "stay_to": "2027-06-14T18:00",
        })
        membership = Membership.objects.get(pk=membership.pk)
        stay = membership.visit
        assert stay is not None and stay.status == Match.STATUS_PENDING
        assert _days(membership) == ("2027-06-01", "2027-06-14") and membership.visit_proposal().sender == ole
        assert Notification.objects.filter(recipient=ambassador, match=membership.match).exists()
        with translation.override("en"):
            page = _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert "Two weeks in June?" in page and "Accept these days" in page
        assert membership.visit_proposal().body == "Two weeks in June?"

        # Accepted in the application: the stay is accepted, its own conversation says so
        _client(ambassador).post(_url("accept_visit_days", membership))
        stay.refresh_from_db()
        assert stay.status == Match.STATUS_ACCEPTED and Membership.objects.get(pk=membership.pk).visit_agreed()
        assert stay.thread.filter(sender=ambassador, status_to=Match.STATUS_ACCEPTED).exists()

    def test_the_stay_is_answered_in_the_application(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        _client(ambassador).post(_url("visit_days", membership), {"visit_from": "2027-05-03", "visit_to": "2027-05-17"})
        _client(ole).post(reverse("communities:volunteer_request", args=[community.slug]), {
            "volunteer_mode": "offer", "stay_from": "2027-06-01T10:00", "stay_to": "2027-06-14T18:00",
        })
        membership = Membership.objects.get(pk=membership.pk)
        with translation.override("en"):
            # Nothing typed: a line says what it is
            assert membership.visit_proposal().body == "I asked for a volunteer stay on these days."
        # Answering it on the stay page leads to the application instead
        stay = membership.visit
        response = _client(ambassador).post(stay.get_absolute_url(), {"action": "accept"})
        stay.refresh_from_db()
        assert response.url.startswith(membership.match.get_absolute_url()) and stay.status == Match.STATUS_PENDING

    def test_days_that_end_before_they_start_are_refused(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        _client(ambassador).post(_url("visit_days", membership), {"visit_from": "2027-06-10", "visit_to": "2027-06-01"})
        assert Membership.objects.get(pk=membership.pk).visit_proposal() is None

    def test_a_tour_from_the_visit_takes_it_over(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        _client(ambassador).post(_url("visit_days", membership), {"visit_from": "2027-06-01", "visit_to": "2027-06-14"})
        _client(ole).post(_url("accept_visit_days", membership))
        stay = Membership.objects.get(pk=membership.pk).visit
        with translation.override("en"):
            page = _client(ole).get(membership.match.get_absolute_url()).content.decode()
        assert "Start a Community-Tour with this stay" in page and "Good for your application, too" in page
        _client(ole).post(reverse("tours:create") + f"?stay={stay.pk}", {"title": "To Hof Kleeblatt", "travel_mode": "train"})
        stay.refresh_from_db()
        assert stay.tour_stop.community == community

    def test_others_on_a_tour_visit_dont_see_the_application(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        olga = _user("olga@example.com", "Olga")
        visit = create_stay(olga, community, companions=[ole], status=Match.STATUS_ACCEPTED)
        assert community.applications_visiting(visit, ambassador) == [membership]
        assert community.applications_visiting(visit, ole) == [membership]
        assert community.applications_visiting(visit, olga) == []


@pytest.mark.django_db
class TestBecomingAMember:
    def test_make_member_remembers_the_visit(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        start = timezone.now() - timedelta(days=20)
        stay = create_stay(ole, community, stay_from=start, stay_to=start + timedelta(days=7), status=Match.STATUS_ACCEPTED)
        # Not the applicant: nothing happens
        assert _client(ole).post(reverse("communities:make_member", args=[community.slug, membership.pk])).status_code == 403

        _client(ambassador).post(reverse("communities:make_member", args=[community.slug, membership.pk]))
        membership.refresh_from_db()
        assert community.is_member(ole) and membership.visit == stay
        assert membership.match.thread.filter(sender=ambassador, body__contains="is a member of Hof Kleeblatt now").exists()

    def test_a_visit_still_ahead_isnt_remembered(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        create_stay(ole, community, stay_from=timezone.now() + timedelta(days=10), status=Match.STATUS_ACCEPTED)
        membership.make_member()
        assert membership.visit is None

    def test_inviting_completes_the_application(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        response = _client(ambassador).get(reverse("communities:api-people", args=[community.slug]) + "?q=Ole")
        assert [person["id"] for person in response.json()["results"]] == [ole.pk]
        _client(ambassador).post(reverse("communities:invite", args=[community.slug]), {"user": ole.pk, "message": "Welcome!"})
        assert community.memberships.filter(user=ole).count() == 1
        assert community.is_member(ole)

    def test_i_already_live_here_tells_the_ambassador(self, community, ambassador, ole):
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        with translation.override("en"):
            _client(ole).post(reverse("communities:lives_here", args=[community.slug, membership.pk]))
        assert membership.match.thread.filter(sender=ole, body="I already live here").exists()
        assert not community.is_member(ole)

    def test_the_tour_page_shows_who_became_a_member_if_they_want(self, community, ambassador, ole):
        from tours.models import Stop, Tour

        tour = Tour.objects.create(title="Clay and seeds", organiser=ole)
        stop = Stop.objects.create(tour=tour, community=community, order=0)
        start = timezone.now() - timedelta(days=30)
        stop.visit_match = create_stay(ole, community, stay_from=start, status=Match.STATUS_ACCEPTED)
        stop.save()
        membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
        membership.make_member()
        assert membership.visit == stop.visit_match

        _client(ole).post(reverse("users:update"), {
            "name": "Ole", "email": ole.email, "shows_visit": str(membership.pk),
        })
        membership.refresh_from_db()
        assert membership.shows_visit


@pytest.mark.django_db
def test_make_member_also_ends_the_answer_form(community, ambassador, ole):
    membership = _accept(ambassador, _apply(ole, community), Membership.STAGE_VISIT)
    page = _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
    assert page.count(f'formaction="{_url("make_member", membership)}"') == 1
    own = _client(ole).get(membership.match.get_absolute_url()).content.decode()
    assert _url("make_member", membership) not in own
