"""Two weeks after a gift-circle, whoever got a yes for a wish there is asked whether it
came true: one email per person and gift-circle, answered on a page behind its link (a
click there, so mail programs that open links don't answer). "Yes" marks the wish
covered on ecobasa. Sent by `ask_if_wishes_came_true` once a day (see crontab)."""

from collections import defaultdict
from datetime import timedelta

from django.core import signing
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_noop

from events import kinds

from .emails import _absolute, _send
from .models import Entry

# How long after the gift-circle
AFTER = timedelta(days=14)
# How long the link keeps working
LINK_MAX_AGE = timedelta(days=90)
SALT = "gift_circles.wishes"


def key_for(event, user=None, guest=None):
    return signing.dumps([event.pk, "user" if user is not None else "guest", (user or guest).pk], salt=SALT)


def read_key(key):
    """(event pk, "user" or "guest", their pk), or None for a wrong or old link."""
    try:
        event_pk, side, pk = signing.loads(key, salt=SALT, max_age=LINK_MAX_AGE)
    except (signing.BadSignature, ValueError, TypeError):
        return None
    return event_pk, side, pk


def wishes_of(event, side, pk):
    """Their fulfilled wishes at it."""
    lines = Entry.objects.filter(event=event, type=Entry.TYPE_WISH, state=Entry.STATE_FULFILLED).select_related(
        "for_user", "for_guest", "listing", "match",
    )
    return lines.filter(from_user_id=pk) if side == "user" else lines.filter(from_guest_id=pk)


def answer(entry, came_true):
    entry.came_true = came_true
    entry.save(update_fields=["came_true"])
    listing = entry.listing
    if came_true and listing is not None and listing.is_wish and listing.covered_at is None:
        listing.covered_at = timezone.now()
        listing.save(update_fields=["covered_at"])


def due(today=None):
    """Fulfilled wishes of gift-circles two weeks ago or longer, closed, not asked yet."""
    today = today or timezone.localdate()
    return Entry.objects.filter(
        event__kind=kinds.GIFT_CIRCLE, event__starts_on__lte=today - AFTER, event__giftsheet__closed_at__isnull=False,
        type=Entry.TYPE_WISH, state=Entry.STATE_FULFILLED, asked_at=None, came_true=None,
    ).exclude(from_user=None, from_guest=None).select_related("event", "from_user", "from_guest", "for_user", "for_guest")


def send_questions(today=None):
    """One email to each person with wishes due, per gift-circle. Returns how many went."""
    grouped = defaultdict(list)
    for entry in due(today):
        grouped[(entry.event, entry.from_user, entry.from_guest)].append(entry)
    sent = 0
    now = timezone.now()
    for (event, user, guest), lines in grouped.items():
        recipient = user or guest
        if recipient.email:
            _send_question(event, recipient, lines, key_for(event, user, guest))
            sent += 1
        Entry.objects.filter(pk__in=[entry.pk for entry in lines]).update(asked_at=now)
    return sent


def _send_question(event, recipient, lines, key):
    subject = gettext_noop("Did your wish come true?") if len(lines) == 1 else gettext_noop("Did your wishes come true?")
    _send(
        event, recipient, "wishes", subject, place_name="", calendar=False, entries=lines,
        answer_url=_absolute(reverse("gift_circles:wishes", args=[event.slug, key])),
    )
