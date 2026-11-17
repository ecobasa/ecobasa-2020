"""Keeping events current: dated events are archived once they end, and are left alone
until then. An ongoing event (no end date) that has run and that nobody updated or
confirmed for EVENT_STALE_DAYS gets an "Is this still current?" email to whoever answers
for it (one click confirms it), and is archived if nobody confirms it within
EVENT_ARCHIVE_GRACE_DAYS. Old entries are what kill a directory; a short, current
one is worth more than a long, outdated one. Run daily by `archive_stale_events`."""

from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone, translation

from .models import Event

TOKEN_SALT = "events-confirm"
# The link keeps working a little longer than the grace period, so a late click still
# brings the event back
TOKEN_MAX_AGE = timedelta(days=60)


def make_confirm_token(event):
    return signing.dumps(event.pk, salt=TOKEN_SALT)


def read_confirm_token(token):
    return signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def send_stale_reminder(event):
    """Ask whoever answers for the event whether it is still current. False if there is
    nobody to ask."""
    manager = event.manager
    if manager is None or not manager.email:
        return False
    with translation.override(manager.language or settings.LANGUAGE_CODE):
        texts = event.texts
        subject = texts["reminder_subject"] % {"title": event.title}
        context = {
            "event": event,
            "recipient": manager,
            "headline": subject,
            "question": texts["reminder_question"] % {"title": event.title, "community": event.community.name},
            "archive_on": timezone.now() + timedelta(days=settings.EVENT_ARCHIVE_GRACE_DAYS),
            "confirm_url": _absolute(event.url("confirm_by_email", make_confirm_token(event))),
            "edit_url": _absolute(event.url("edit")),
            "detail_url": _absolute(event.get_absolute_url()),
        }
        text_body = render_to_string("events/email/stale_reminder.txt", context)
        html_body = render_to_string("events/email/stale_reminder.html", context)
    message = EmailMultiAlternatives(
        subject=str(subject), body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[manager.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)
    return True


def archive_stale_events(now=None):
    """Archive ended and unconfirmed events, and remind about stale ones.
    Returns (archived, reminded)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    live = Event.objects.filter(archived_at=None)

    # Ended: archived without asking (archived_at only, so they don't look updated)
    archived = live.filter(ends_on__lt=today).update(archived_at=now)

    stale_before = now - timedelta(days=settings.EVENT_STALE_DAYS)
    grace_before = now - timedelta(days=settings.EVENT_ARCHIVE_GRACE_DAYS)
    # Only ongoing ones that have been running that long: people rarely update an event
    # with its days ahead
    stale = live.filter(ends_on=None, updated_at__lt=stale_before).filter(
        Q(starts_on=None) | Q(starts_on__lt=timezone.localdate(stale_before))
    )
    # Reminded a while ago and still not confirmed
    archived += stale.filter(stale_reminder_sent_at__lt=grace_before).update(archived_at=now)

    reminded = 0
    for event in stale.filter(stale_reminder_sent_at=None).select_related("community__ambassador"):
        if send_stale_reminder(event):
            reminded += 1
        # Also without anybody to ask, so the grace period starts
        Event.objects.filter(pk=event.pk).update(stale_reminder_sent_at=now)
    return archived, reminded
