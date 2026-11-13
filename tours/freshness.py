"""Keeping tours current: tours are archived TOUR_ARCHIVE_AFTER_DAYS after their last
day. A published tour idea (no stops with days yet) that nobody updated or confirmed for
TOUR_IDEA_STALE_DAYS gets one "Is this still current?" email to its organisers (one click
confirms it), and is archived if nobody confirms it within TOUR_IDEA_ARCHIVE_GRACE_DAYS.
Dated tours need no reminder: their days say when they are over. Run daily by
`archive_stale_tours`."""

from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Tour

TOKEN_SALT = "tours-confirm"
# The link keeps working a little longer than the grace period, so a late click still
# brings the tour back
TOKEN_MAX_AGE = timedelta(days=60)


def make_confirm_token(tour):
    return signing.dumps(tour.pk, salt=TOKEN_SALT)


def read_confirm_token(token):
    return signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def send_stale_reminder(tour):
    """Ask the organisers whether the tour idea is still current, each in their
    language. False if there is nobody to ask."""
    sent = False
    for organiser in tour.organisers():
        if not organiser.email:
            continue
        with translation.override(organiser.language or settings.LANGUAGE_CODE):
            subject = _("Is your tour idea “%(title)s” still current?") % {"title": tour.title}
            context = {
                "tour": tour,
                "recipient": organiser,
                "headline": subject,
                "archive_on": timezone.now() + timedelta(days=settings.TOUR_IDEA_ARCHIVE_GRACE_DAYS),
                "confirm_url": _absolute(tour.url("confirm_by_email", make_confirm_token(tour))),
                "plan_url": _absolute(tour.url("plan")),
                "detail_url": _absolute(tour.get_absolute_url()),
            }
            text_body = render_to_string("tours/email/stale_reminder.txt", context)
            html_body = render_to_string("tours/email/stale_reminder.html", context)
        message = EmailMultiAlternatives(
            subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[organiser.email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=True)
        sent = True
    return sent


def archive_stale_tours(now=None):
    """Archive tours that are over and tour ideas nobody confirmed, and remind about
    stale ideas. Returns (archived, reminded)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    live = Tour.objects.filter(archived_at=None)

    # Over for a while (they often go on a few days longer): archived without asking
    # (archived_at only, so they don't look updated)
    over_before = today - timedelta(days=settings.TOUR_ARCHIVE_AFTER_DAYS)
    archived = live.filter(ends_on__lt=over_before).update(archived_at=now)

    stale_before = now - timedelta(days=settings.TOUR_IDEA_STALE_DAYS)
    grace_before = now - timedelta(days=settings.TOUR_IDEA_ARCHIVE_GRACE_DAYS)
    # Drafts are only their organisers' notes, nobody else sees them
    stale = live.filter(starts_on=None, ends_on=None, updated_at__lt=stale_before).exclude(published_at=None)
    # Reminded a while ago and still not confirmed
    archived += stale.filter(stale_reminder_sent_at__lt=grace_before).update(archived_at=now)

    reminded = 0
    for tour in stale.filter(stale_reminder_sent_at=None):
        if send_stale_reminder(tour):
            reminded += 1
        # Also without anybody to ask, so the grace period starts
        Tour.objects.filter(pk=tour.pk).update(stale_reminder_sent_at=now)
    return archived, reminded
