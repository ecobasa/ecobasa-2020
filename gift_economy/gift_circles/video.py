"""The video call of an online gift-circle: a room on the Jitsi server (JITSI_BASE_URL)
with a name nobody guesses, shown on a page of ecobasa to who comes and its host, from an
hour before. Emails link to that page, never to the room: what people get comes from
ecobasa, and the room stays unknown to whoever isn't in it. An hour before, who comes
gets the link once more (`send_video_call_links`, every 5 minutes, see crontab)."""

import hashlib
import hmac
import json
from datetime import datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_noop

from events import kinds
from events.models import Event

from . import bringing
from .emails import _guest_urls, _send

# How long before it starts its page shows the room
OPENS_BEFORE = timedelta(hours=1)

SUBJECT = gettext_noop("In an hour: %(title)s")


def room_url(event):
    """Its room: one of its own on the server, named from the secret key so it can't be
    guessed from its address; the host's own link where it has one."""
    if event.video_url:
        return event.video_url
    name = hmac.new(settings.SECRET_KEY.encode(), f"gift-circle-{event.pk}".encode(), hashlib.sha256).hexdigest()[:24]
    return f"{settings.JITSI_BASE_URL.rstrip('/')}/ecobasa-{name}"


def embeds(event):
    """Whether its page shows the room itself: the server lets ecobasa embed it."""
    return settings.JITSI_EMBED and room_url(event).startswith(settings.JITSI_BASE_URL.rstrip("/") + "/")


def embed_url(event, name=""):
    """The room for the page: no "download the app" on phones, and `name` filled in."""
    params = ["config.disableDeepLinking=true"]
    if name:
        params.append("userInfo.displayName=" + quote(json.dumps(name)))
    return room_url(event) + "#" + "&".join(params)


def _zone(event):
    return event.zone or ZoneInfo(settings.TIME_ZONE)


def starts(event):
    """When it starts, in its timezone; None without a day. Without an hour, at the start
    of the day."""
    if event.starts_on is None:
        return None
    return datetime.combine(event.starts_on, event.starts_at or time.min, tzinfo=_zone(event))


def opens(event):
    start = starts(event)
    return start - OPENS_BEFORE if start else None


def is_open(event, now=None):
    """Whether its room is shown: from an hour before until the end of its last day."""
    opening = opens(event)
    if opening is None or event.archived_at:
        return False
    now = now or timezone.now()
    last = datetime.combine(event.ends_on or event.starts_on, time.max, tzinfo=_zone(event))
    return opening <= now <= last


def send_links(now=None):
    """To everyone who comes to an online gift-circle opening now, and its host, once.
    Returns how many emails went."""
    from .reminders import recipients

    now = now or timezone.now()
    today = timezone.localdate(now)
    circles = Event.objects.filter(
        kind=kinds.GIFT_CIRCLE, is_online=True, archived_at=None, video_call_mailed_at=None,
        # Timezones apart from the server's: a day either side
        starts_on__range=(today - timedelta(days=1), today + timedelta(days=1)),
    ).select_related("community__ambassador", "host_user", "host_tour__organiser")
    sent = 0
    for event in circles:
        if not is_open(event, now):
            continue
        # Before the emails: a run that fails halfway doesn't mail anyone twice
        Event.objects.filter(pk=event.pk).update(video_call_mailed_at=now)
        people, guests = recipients(event)
        for person in people:
            _send(event, person, "video_call", SUBJECT, calendar=False, is_host=person == event.manager)
        for guest in guests:
            _send(event, guest, "video_call", SUBJECT, calendar=False, is_guest=True, **_guest_urls(guest))
        sent += len(people) + len(guests)
    return sent


def may_join(event, user):
    """Who comes with an account, and its host."""
    return bringing.is_in(event, user)
