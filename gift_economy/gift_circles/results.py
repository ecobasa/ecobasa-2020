"""After a gift-circle: everyone who came gets the results once its Giftsheet is closed,
the whole Giftsheet and their own part in it, with how to reach the other side of each
line. The one who wished follows up. A Giftsheet nobody closed is closed the morning
after by `send_gift_circle_results` (see crontab)."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_noop

from events import kinds

from . import giftsheet as sheets
from .bringing import coming_ids
from .emails import _absolute, _guest_urls, _send
from .models import Entry, Giftsheet, Idea

SUBJECT = gettext_noop("What came out of %(title)s")

# What a line is to someone who has a part in it
WISH_HELPED = "wish_helped"  # their wish, and someone said yes
SAID_YES = "said_yes"  # they said yes to someone's wish, or their offer was taken
TAKES = "takes"  # they take someone's offer
IDEA_FOR_THEM = "idea_for_them"  # an idea for their line
THEIR_IDEA = "their_idea"  # their idea for someone's line


@dataclass
class Part:
    """One line from someone's side: `kind` above, the line, the idea if it is about one,
    the other side's name and how to reach them (`contact`: (how, url or address) or
    None)."""

    kind: str
    entry: Entry
    other_name: str
    contact: tuple = None
    idea: Idea = None


def _is(user_id, guest_id, user, guest):
    return (user is not None and user_id == user.pk) or (guest is not None and guest_id == guest.pk)


def parts(event, user=None, guest=None):
    """The lines `user` (or `guest`) has a part in, in the Giftsheet's order."""
    found = []
    for entry in sheets.entries(event):
        mine = _is(entry.from_user_id, entry.from_guest_id, user, guest)
        theirs = _is(entry.for_user_id, entry.for_guest_id, user, guest)
        if entry.state == Entry.STATE_FULFILLED and (mine or theirs):
            if mine:
                kind = SAID_YES if entry.is_offer else WISH_HELPED
                other = (entry.for_user, entry.for_guest, entry.for_name)
            else:
                kind = TAKES if entry.is_offer else SAID_YES
                other = (entry.from_user, entry.from_guest, entry.from_name)
            found.append(_part(event, kind, entry, other, user, guest))
        for idea in entry.ideas.all():
            if mine and not _is(idea.from_user_id, idea.from_guest_id, user, guest):
                found.append(_part(event, IDEA_FOR_THEM, entry, (idea.from_user, idea.from_guest, idea.from_name), user, guest, idea))
            elif _is(idea.from_user_id, idea.from_guest_id, user, guest) and not mine:
                found.append(_part(event, THEIR_IDEA, entry, (entry.from_user, entry.from_guest, entry.from_name), user, guest, idea))
    return found


def _part(event, kind, entry, other, user, guest, idea=None):
    other_user, other_guest, other_name = other
    name = other_user.name or other_user.email if other_user else other_guest.name if other_guest else other_name
    return Part(kind, entry, name, contact(event, entry, other_user, other_guest, user, guest, idea), idea)


def contact(event, entry, other_user, other_guest, user=None, guest=None, idea=None):
    """How `user` (or `guest`) reaches the other side of a line: the match's conversation
    if both are in it, a message on ecobasa between two members, the email of a guest who
    let the people they make a match with have it, else "Write to them" on ecobasa, which
    mails them without showing an address. None for someone known only by name."""
    if user is not None and other_user is not None:
        match = entry.match if idea is None else None
        if match is not None and {match.from_user_id, match.recipient_id} == {user.pk, other_user.pk}:
            return ("thread", _absolute(reverse("matches:detail", args=[match.pk])))
        return ("message", _absolute(reverse("postman:write_with_recipients", args=[str(other_user.pk)])))
    if other_guest is not None and other_guest.share_email:
        return ("email", other_guest.email)
    if other_user is None and other_guest is None:
        return None
    return ("write", _absolute(write_url(event, entry, other_user, other_guest, guest)))


def write_url(event, entry, other_user, other_guest, guest=None):
    """The "Write to them" form: a guest's through their link."""
    to = f"user:{other_user.pk}" if other_user is not None else f"guest:{other_guest.pk}"
    if guest is not None:
        path = reverse("gift_circles:guest_write", args=[event.slug, guest.token, entry.pk])
    else:
        path = reverse("gift_circles:write", args=[event.slug, entry.pk])
    return f"{path}?to={to}"


def recipients(event):
    """(people with an account, guests) who came or are on the Giftsheet, the host first."""
    ids = coming_ids(event)
    ids.update(event.entries.exclude(from_user=None).values_list("from_user_id", flat=True))
    ids.update(event.entries.exclude(for_user=None).values_list("for_user_id", flat=True))
    ids.update(Idea.objects.filter(entry__event=event).exclude(from_user=None).values_list("from_user_id", flat=True))
    manager = event.manager
    if manager is not None:
        ids.discard(manager.pk)
    people = list(get_user_model().objects.filter(pk__in=ids))
    if manager is not None:
        people.insert(0, manager)
    return [person for person in people if person.email], list(event.guests.coming())


def send_result(event, recipient, guest=False):
    user, guest_row = (None, recipient) if guest else (recipient, None)
    own = parts(event, user, guest_row)
    lines = list(sheets.entries(event))
    staying = [
        entry for entry in lines
        if not guest and entry.state == Entry.STATE_OPEN and entry.listing_id and entry.from_user_id == recipient.pk
    ]
    extra = {
        "parts": own, "entries": lines, "staying": bool(staying), "is_guest": guest,
        "has_photos": event.giftsheet_photos.exists(),
        "stories_url": _absolute(event.get_absolute_url()) + "#references",
    }
    if guest:
        extra.update(_guest_urls(recipient))
        extra["giftsheet_url"] = _absolute(reverse("gift_circles:guest_giftsheet", args=[event.slug, recipient.token]))
    else:
        extra["giftsheet_url"] = _absolute(reverse("gift_circles:giftsheet", args=[event.slug]))
        extra["next_url"] = _absolute(reverse("gift_circles:next", args=[event.slug]))
    _send(event, recipient, "results", SUBJECT, place_name="", calendar=False, **extra)


def send_results(event):
    """To everyone who came: their part and the whole Giftsheet. Returns how many went."""
    people, guests = recipients(event)
    for person in people:
        send_result(event, person)
    for guest in guests:
        send_result(event, guest, guest=True)
    return len(people) + len(guests)


def close_forgotten(today=None):
    """The Giftsheets of gift-circles before today still open, with lines on them: closed
    now, and their results sent if they weren't before. Returns how many were closed."""
    today = today or timezone.localdate()
    open_sheets = Giftsheet.objects.filter(
        closed_at=None, event__kind=kinds.GIFT_CIRCLE, event__starts_on__lt=today, event__entries__isnull=False,
    ).distinct().select_related("event__community__ambassador", "event__host_user", "event__host_tour__organiser")
    closed = 0
    for sheet in open_sheets:
        sheets.close(sheet.event, sheet)
        closed += 1
    return closed

