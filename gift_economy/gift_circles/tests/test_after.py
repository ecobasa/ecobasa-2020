"""After a gift-circle: the results email with everyone's part and how to reach each
other, "Write to them", closing a forgotten Giftsheet the morning after, guests' lines
moving to their account, "Did your wish come true?", how it went, and planning the next
one."""
from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from gift_economy.gift_circles import results, wishes
from gift_economy.gift_circles.models import Entry, Guest, Idea, Invitation
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match
from gift_economy.references.models import Reference
from users.models import User

from .test_giftsheet import (  # noqa: F401
    _add, _circle, _client, _come, _entry_url, _guest, _url, host, other, person, stranger,
)

pytestmark = pytest.mark.django_db


def _close(user, event, capture):
    with capture(execute=True):
        return _client(user).post(reverse("gift_circles:giftsheet_close", args=[event.slug]))


def _answer(event, entry, who):
    _client(event.manager).post(_entry_url(event, entry), {"action": "fulfilled", "who": who})


def _yesterday(event):
    """It was yesterday: coming is only possible ahead, so it is moved there after."""
    day = timezone.localdate() - timedelta(days=1)
    Event.objects.filter(pk=event.pk).update(starts_on=day, ends_on=day)
    event.refresh_from_db()
    return event


def _mail_to(email):
    return next(message for message in mail.outbox if message.to == [email])


@pytest.fixture
def circle(host, person, other):
    """Yesterday: Tomek (keeps his lines on ecobasa) and Ayla came, and Lena as a guest
    who keeps her email; Tomek's sofa wish got a yes from Ayla, Lena's bike repair was
    taken by Tomek, Ayla had an idea for Tomek's ride."""
    event = _circle(host)
    _come(event, person, keep=True)
    _come(event, other)
    _yesterday(event)
    lena = _guest(event)
    _add(host, event, "Help moving a sofa", who=f"user:{person.pk}")
    _add(host, event, "Bike repair", type="offer", who=f"guest:{lena.pk}")
    _add(host, event, "A ride to Lübeck", who=f"user:{person.pk}")
    sofa, bike, ride = Entry.objects.order_by("pk")
    _answer(event, sofa, f"user:{other.pk}")
    _answer(event, bike, f"user:{person.pk}")
    Idea.objects.create(entry=ride, from_user=other, text="Ask at the station")
    return event


def test_closing_sends_everyone_their_part_once(circle, host, person, other, django_capture_on_commit_callbacks):
    response = _close(host, circle, django_capture_on_commit_callbacks)
    assert response.status_code == 302
    assert {tuple(message.to) for message in mail.outbox} == {
        ("mira@example.com",), ("tomek@example.com",), ("ayla@example.com",), ("lena@example.com",),
    }
    sofa, bike, ride = Entry.objects.order_by("pk")

    text = _mail_to("tomek@example.com").body
    # Ayla kept her lines off ecobasa, so no match: a message on ecobasa
    assert reverse("postman:write_with_recipients", args=[str(other.pk)]) in text
    # Lena didn't share her email: "Write to her" without it
    assert "lena@example.com" not in text
    assert reverse("gift_circles:write", args=[circle.slug, bike.pk]) + f"?to=guest:{bike.from_guest_id}" in text
    assert reverse("gift_circles:next", args=[circle.slug]) in text

    lena = _mail_to("lena@example.com").body
    assert reverse("gift_circles:guest_write", args=[circle.slug, bike.from_guest.token, bike.pk]) + f"?to=user:{person.pk}" in lena
    assert reverse("gift_circles:next", args=[circle.slug]) not in lena

    # Open again and closed again: nobody is mailed twice
    mail.outbox.clear()
    _client(host).post(reverse("gift_circles:giftsheet_close", args=[circle.slug]), {"action": "reopen"})
    _close(host, circle, django_capture_on_commit_callbacks)
    assert mail.outbox == []


def test_a_match_s_conversation_and_a_shared_email_are_the_contacts(host, person, other, django_capture_on_commit_callbacks):
    event = _circle(host)
    _come(event, person, keep=True)
    _come(event, other, keep=True)
    _yesterday(event)
    lena = _guest(event)
    lena.share_email = True
    lena.save()
    _add(host, event, "Help moving a sofa", who=f"user:{person.pk}")
    _add(host, event, "Jam jars", type="offer", who=f"guest:{lena.pk}")
    sofa, jars = Entry.objects.order_by("pk")
    _answer(event, sofa, f"user:{other.pk}")
    _answer(event, jars, f"user:{person.pk}")
    _close(host, event, django_capture_on_commit_callbacks)
    sofa.refresh_from_db()
    text = _mail_to("tomek@example.com").body
    assert reverse("matches:detail", args=[sofa.match_id]) in text
    assert "Email: lena@example.com" in text


def test_the_morning_after_a_forgotten_giftsheet_is_closed(circle, host, django_capture_on_commit_callbacks):
    today = _circle(host, title="Today's gift-circle")
    _add(host, today, "Seeds", who=f"user:{host.pk}")
    empty = _circle(host, days=-2, title="Nobody wrote anything")
    _client(host).get(_url(empty))
    with django_capture_on_commit_callbacks(execute=True):
        assert results.close_forgotten() == 1
    circle.giftsheet.refresh_from_db()
    assert circle.giftsheet.is_closed and circle.giftsheet.closed_by is None
    assert len(mail.outbox) == 4
    assert not today.giftsheet.is_closed
    # A person's lines who said yes are on ecobasa
    assert Entry.objects.get(text="Help moving a sofa").listing.owner.name == "Tomek"


def test_write_to_them_mails_the_other_side_without_their_address(circle, host, person, other, stranger, django_capture_on_commit_callbacks):
    _close(host, circle, django_capture_on_commit_callbacks)
    mail.outbox.clear()
    sofa, bike, ride = Entry.objects.order_by("pk")
    lena = bike.from_guest

    url = reverse("gift_circles:write", args=[circle.slug, bike.pk]) + f"?to=guest:{lena.pk}"
    assert "lena@example.com" not in _client(person).get(url).content.decode()
    _client(person).post(url, {"message": "When could I bring my bike?"})
    message = mail.outbox[-1]
    assert message.to == ["lena@example.com"] and message.reply_to == ["tomek@example.com"]
    assert "When could I bring my bike?" in message.body

    # Lena answers through her link
    guest_url = reverse("gift_circles:guest_write", args=[circle.slug, lena.token, bike.pk]) + f"?to=user:{person.pk}"
    Client().post(guest_url, {"message": "Saturday?"})
    assert mail.outbox[-1].to == ["tomek@example.com"] and mail.outbox[-1].reply_to == ["lena@example.com"]

    # Only the sides of a line: not Ayla to Lena, not about a line they aren't on
    count = len(mail.outbox)
    _client(other).post(url, {"message": "Hello"})
    _client(stranger).post(url, {"message": "Hello"})
    _client(person).post(reverse("gift_circles:write", args=[circle.slug, sofa.pk]) + f"?to=guest:{lena.pk}", {"message": "Hi"})
    assert len(mail.outbox) == count


def test_write_to_them_waits_for_the_giftsheet_to_close(circle, person):
    bike = Entry.objects.get(text="Bike repair")
    url = reverse("gift_circles:write", args=[circle.slug, bike.pk]) + f"?to=guest:{bike.from_guest_id}"
    assert _client(person).post(url, {"message": "Hi"}).url == _url(circle)
    assert mail.outbox == []


def test_a_guest_s_account_takes_their_lines_along(circle, host, person, django_capture_on_commit_callbacks):
    lena = Guest.objects.get()
    lena.keep_on_ecobasa = True
    lena.save()
    _close(host, circle, django_capture_on_commit_callbacks)
    bike = Entry.objects.get(text="Bike repair")
    assert bike.listing is None and bike.match is None

    client = Client()
    client.get(reverse("gift_circles:guest_account", args=[circle.slug, lena.token]))
    user = User.objects.create_user(email="lena@example.com", password="secret", name="Lena")
    client.post(reverse("users:login"), {"username": "lena@example.com", "password": "secret"})
    bike.refresh_from_db()
    assert (bike.from_user, bike.from_guest) == (user, None)
    assert bike.listing.owner == user and bike.listing.title == "Bike repair"
    assert (bike.match.from_user, bike.match.recipient, bike.match.status) == (person, user, Match.STATUS_ACCEPTED)


def test_two_weeks_later_who_wished_is_asked(circle, host, person, other, django_capture_on_commit_callbacks):
    _close(host, circle, django_capture_on_commit_callbacks)
    mail.outbox.clear()
    assert wishes.send_questions() == 0

    later = timezone.localdate() + timedelta(days=13)
    assert wishes.send_questions(later) == 1
    question = mail.outbox[-1]
    assert question.to == ["tomek@example.com"]
    # Once
    assert wishes.send_questions(later) == 0

    sofa = Entry.objects.get(text="Help moving a sofa")
    url = reverse("gift_circles:wishes", args=[circle.slug, wishes.key_for(circle, user=person)])
    assert Client().get(url).status_code == 200
    # Nothing is answered by opening the link
    sofa.refresh_from_db()
    assert sofa.came_true is None

    Client().post(url, {"entry": sofa.pk, "answer": "no"})
    sofa.refresh_from_db()
    assert sofa.came_true is False

    Client().post(url, {"entry": sofa.pk, "answer": "yes"})
    sofa.refresh_from_db()
    assert sofa.came_true is True


def test_a_wrong_wishes_link_finds_nothing(circle, person):
    other_circle = _circle(circle.manager, days=-1, title="Another one")
    url = reverse("gift_circles:wishes", args=[other_circle.slug, wishes.key_for(circle, user=person)])
    assert Client().get(url).url == other_circle.get_absolute_url()
    assert Client().get(reverse("gift_circles:wishes", args=[circle.slug, "nothing"])).url == circle.get_absolute_url()


def test_who_came_plans_the_next_one(circle, host, person, other, stranger, django_capture_on_commit_callbacks):
    url = reverse("gift_circles:next", args=[circle.slug])
    assert _client(stranger).get(url).url == circle.get_absolute_url()
    ahead = _circle(host, days=3, title="Next week")
    assert _client(host).get(reverse("gift_circles:next", args=[ahead.slug])).url == ahead.get_absolute_url()

    form = _client(other).get(url).context["form"]
    assert form.initial["title"] == "Gift-circle in the park"

    day = timezone.localdate() + timedelta(days=28)
    data = {
        "kind": circle.kind, "title": "Gift-circle in the park", "starts_on": day.isoformat(),
        "starts_at": "18:00", "ends_at": "19:30", "is_open": "on",
        "location_name": circle.location_name, "location": circle.location.ewkt,
    }
    with django_capture_on_commit_callbacks(execute=True):
        response = _client(other).post(url, data)
    following = Event.objects.get(previous=circle)
    assert response.url == following.get_absolute_url()
    assert (following.host_user, following.starts_on) == (other, day)
    invited = Invitation.objects.filter(event=following)
    assert {invitation.user for invitation in invited.exclude(user=None)} == {host, person}
    assert [invitation.email for invitation in invited.filter(user=None)] == ["lena@example.com"]


def test_who_came_tells_how_it_went_about_something_of_it(circle, host, person, other, stranger, django_capture_on_commit_callbacks):
    _close(host, circle, django_capture_on_commit_callbacks)
    url = reverse("gift_circles:story", args=[circle.slug])

    # About the idea: on the gift-circle's page and on Ayla's profile
    idea = Idea.objects.get()
    _client(person).post(url, {"about": f"idea:{idea.pk}", "impression": "positive", "text": "The station had a ride for me."})
    story = Reference.objects.get()
    assert (story.author, story.subject, story.place, story.recipient) == (person, idea, circle, other)

    # About the host, and about the gift-circle itself
    _client(person).post(url, {"about": f"user:{host.pk}", "impression": "positive", "text": "Mira kept us in time."})
    _client(person).post(url, {"about": "event", "impression": "positive", "text": "A warm evening."})
    assert Reference.objects.get(text="Mira kept us in time.").subject == host
    assert Reference.objects.get(text="A warm evening.").subject == circle

    # Not about oneself, not by someone who wasn't there
    _client(person).post(url, {"about": f"user:{person.pk}", "impression": "positive", "text": "Me"})
    _client(stranger).post(url, {"about": "event", "impression": "positive", "text": "Spam"})
    assert Reference.objects.count() == 3

    # Taken back
    _client(person).post(url, {"action": "delete", "reference": story.pk})
    assert not Reference.objects.filter(pk=story.pk).exists()


def test_a_tool_lent_at_the_circle_becomes_a_loan_at_the_giver_s_place(host, person, other, django_capture_on_commit_callbacks):
    event = _circle(host)
    _come(event, person, keep=True)
    _come(event, other, keep=True)
    _add(host, event, "A drill", type="offer", who=f"user:{other.pk}")
    _add(host, event, "Help with the garden", who=f"user:{person.pk}")
    _add(host, event, "A ladder", who=f"user:{person.pk}")
    drill, garden, ladder = Entry.objects.order_by("pk")
    day = timezone.localdate() + timedelta(days=3)
    _client(host).post(_entry_url(event, drill), {
        "action": "fulfilled", "who": f"user:{person.pk}", "lends": "on",
        "borrow_from": day.isoformat(), "borrow_to": (day - timedelta(days=1)).isoformat(),
    })
    drill.refresh_from_db()
    assert drill.state == Entry.STATE_OPEN
    for entry in (drill, ladder):
        _client(host).post(_entry_url(event, entry), {
            "action": "fulfilled", "who": f"user:{other.pk if entry == ladder else person.pk}", "lends": "on",
            "borrow_from": day.isoformat(), "borrow_to": (day + timedelta(days=2)).isoformat(),
        })
    _answer(event, garden, f"user:{other.pk}")
    drill.refresh_from_db()
    assert (drill.borrow_from, drill.borrow_to) == (day, day + timedelta(days=2))

    _close(host, event, django_capture_on_commit_callbacks)
    for entry in (drill, garden, ladder):
        entry.refresh_from_db()
    # Ayla's drill to lend stays on ecobasa, lent to Tomek, at her place
    assert drill.listing.lend and drill.listing.is_offer and drill.listing.covered_at is None
    assert drill.match.is_loan and timezone.localdate(drill.match.loan.starts_at) == day
    assert (drill.match.lender, drill.match.borrower) == (other, person)
    assert drill.match.location_type == Match.LOC_YOUR_PLACE and drill.match.recipient == other

    # Tomek's ladder wish, met by Ayla lending hers: her ladder to lend stays, his wish isn't kept
    assert ladder.listing.owner == other and ladder.listing.is_offer and ladder.listing.lend
    assert not Listing.objects.filter(owner=person, title="A ladder").exists()
    assert (ladder.match.from_user, ladder.match.recipient, ladder.match.lender) == (person, other, other)
    assert ladder.match.location_type == Match.LOC_YOUR_PLACE

    # The garden wish is met: no longer current; at Ayla's place, who fulfilled it
    assert garden.listing.covered_at is not None
    assert garden.match.location_type == Match.LOC_MY_PLACE and garden.match.from_user == other


def test_lending_days_can_be_left_for_the_match(host, person, other, django_capture_on_commit_callbacks):
    event = _circle(host)
    _come(event, person, keep=True)
    _come(event, other, keep=True)
    _add(host, event, "A ladder", who=f"user:{person.pk}")
    ladder = Entry.objects.get()
    _client(host).post(_entry_url(event, ladder), {"action": "fulfilled", "who": f"user:{other.pk}", "lends": "on"})
    ladder.refresh_from_db()
    assert ladder.lend and ladder.borrow_from is None

    _close(host, event, django_capture_on_commit_callbacks)
    ladder.refresh_from_db()
    match = ladder.match
    assert not match.is_loan and match.lends_later and (match.lender, match.borrower) == (other, person)

    # Tomek proposes the days at home, Ayla accepts: now it is a loan
    day = timezone.localdate() + timedelta(days=5)
    _client(person).post(match.get_absolute_url(), {
        "action": "counter", "counter_stay_from": day.isoformat(), "counter_stay_to": (day + timedelta(days=1)).isoformat(),
        "counter_location_type": Match.LOC_YOUR_PLACE,
    })
    match.refresh_from_db()
    assert match.status == Match.STATUS_COUNTER
    _client(other).post(match.get_absolute_url(), {"action": "accept"})
    match = Match.objects.get(pk=match.pk)
    assert match.status == Match.STATUS_ACCEPTED and match.is_loan
    assert timezone.localdate(match.loan.starts_at) == day
