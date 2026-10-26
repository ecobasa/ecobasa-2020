"""Keeping projects current: dated projects are archived once they end; any project nobody
updated or confirmed for PROJECT_STALE_DAYS gets an "Is this still current?" email to its
ambassador (one click confirms it), and is archived if nobody confirms it within
PROJECT_ARCHIVE_GRACE_DAYS. Old entries are what kill a directory; a short, current one
is worth more than a long, outdated one. Run daily by `archive_stale_projects`."""

from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Project

TOKEN_SALT = "projects-confirm"
# The link keeps working a little longer than the grace period, so a late click still
# brings the project back
TOKEN_MAX_AGE = timedelta(days=60)


def make_confirm_token(project):
    return signing.dumps(project.pk, salt=TOKEN_SALT)


def read_confirm_token(token):
    return signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def send_stale_reminder(project):
    """Ask the ambassador whether the project is still current. False if there is nobody
    to ask."""
    owner = project.community.owner
    if owner is None or not owner.email:
        return False
    with translation.override(owner.language or settings.LANGUAGE_CODE):
        subject = _("Is your project “%(title)s” still current?") % {"title": project.title}
        context = {
            "project": project,
            "recipient": owner,
            "headline": subject,
            "archive_on": timezone.now() + timedelta(days=settings.PROJECT_ARCHIVE_GRACE_DAYS),
            "confirm_url": _absolute(reverse("projects:confirm_by_email", args=[make_confirm_token(project)])),
            "edit_url": _absolute(reverse("projects:edit", args=[project.pk])),
            "detail_url": _absolute(project.get_absolute_url()),
        }
        text_body = render_to_string("projects/email/stale_reminder.txt", context)
        html_body = render_to_string("projects/email/stale_reminder.html", context)
    message = EmailMultiAlternatives(
        subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[owner.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)
    return True


def archive_stale_projects(now=None):
    """Archive ended and unconfirmed projects, and remind about stale ones.
    Returns (archived, reminded)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    live = Project.objects.filter(archived_at=None)

    # Ended: archived without asking (archived_at only, so they don't look updated)
    archived = live.filter(ends_on__lt=today).update(archived_at=now)

    stale_before = now - timedelta(days=settings.PROJECT_STALE_DAYS)
    grace_before = now - timedelta(days=settings.PROJECT_ARCHIVE_GRACE_DAYS)
    stale = live.filter(updated_at__lt=stale_before)
    # Reminded a while ago and still not confirmed
    archived += stale.filter(stale_reminder_sent_at__lt=grace_before).update(archived_at=now)

    reminded = 0
    for project in stale.filter(stale_reminder_sent_at=None).select_related("community__owner"):
        if send_stale_reminder(project):
            reminded += 1
        # Also without anybody to ask, so the grace period starts
        Project.objects.filter(pk=project.pk).update(stale_reminder_sent_at=now)
    return archived, reminded
