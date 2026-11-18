"""An event as a calendar file (.ics, RFC 5545), written by hand: a few lines of text
need no library. Dates and hours are local at the place, so the times are "floating"
(without a timezone): a calendar shows them as they are."""

from datetime import timedelta, timezone as tz

from django.conf import settings
from django.utils import timezone


def _escape(text):
    return (
        str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line):
    """Lines of at most 75 octets, continued with a space (RFC 5545 3.1)."""
    encoded = line.encode("utf-8")
    parts = []
    while len(encoded) > 75:
        cut = 75 if not parts else 74
        # Not inside a character
        while cut and (encoded[cut] & 0xC0) == 0x80:
            cut -= 1
        parts.append(encoded[:cut].decode("utf-8"))
        encoded = encoded[cut:]
    parts.append(encoded.decode("utf-8"))
    return "\r\n ".join(parts)


def _when(day, hour):
    if hour is None:
        return ";VALUE=DATE:" + day.strftime("%Y%m%d")
    return ":" + day.strftime("%Y%m%d") + hour.strftime("T%H%M%S")


def ics(event, place_name="", description=""):
    """The calendar file of a dated `event`, at `place_name` (as the one who gets it may
    see it). Without hours it takes whole days."""
    starts_on = event.starts_on or event.ends_on
    ends_on = event.ends_on or starts_on
    domain = settings.SITE_URL.split("://")[-1].strip("/").split(":")[0]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ecobasa.org//events//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:event-{event.pk}@{domain}",
        "DTSTAMP:" + timezone.now().astimezone(tz.utc).strftime("%Y%m%dT%H%M%SZ"),
    ]
    if event.starts_at:
        lines.append("DTSTART" + _when(starts_on, event.starts_at))
        if event.ends_at:
            lines.append("DTEND" + _when(ends_on, event.ends_at))
    else:
        # A whole day ends at the start of the next
        lines.append("DTSTART" + _when(starts_on, None))
        lines.append("DTEND" + _when(ends_on + timedelta(days=1), None))
    lines.append("SUMMARY:" + _escape(event.title))
    if place_name:
        lines.append("LOCATION:" + _escape(place_name))
    url = settings.SITE_URL.rstrip("/") + event.get_absolute_url()
    lines.append("URL:" + url)
    lines.append("DESCRIPTION:" + _escape("\n\n".join(filter(None, [description, url]))))
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
