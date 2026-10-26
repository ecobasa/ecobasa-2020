"""The weekly email with the new matches, for everyone who wants it: who has wishes hears
about offers and skills nearby, who offers or has skills hears about wishes and projects.
Sent by `send_suggestion_emails` (weekly cron); at most one a week per person."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db.models import Max
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import ngettext

UNSUBSCRIBE_SALT = "suggestions-unsubscribe"
MIN_INTERVAL = timedelta(days=6)


def make_unsubscribe_token(user):
    return signing.dumps(user.pk, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token):
    return signing.loads(token, salt=UNSUBSCRIBE_SALT)


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def send_suggestion_email(user, now=None):
    """Email `user` the suggestions not emailed yet (and not dismissed), unless they had
    one less than a week ago. Returns whether an email was sent."""
    now = now or timezone.now()
    last = user.suggestions.aggregate(last=Max("emailed_at"))["last"]
    if last and now - last < MIN_INTERVAL:
        return False
    pending = list(
        user.suggestions.filter(emailed_at=None, dismissed_at=None)
        .select_related("own_type", "other_type").prefetch_related("own", "other")
    )
    found = [s for s in pending if s.other is not None and s.own is not None]
    if not found:
        return False
    with translation.override(user.language or settings.LANGUAGE_CODE):
        subject = ngettext(
            "%(count)s new match near you", "%(count)s new matches near you", len(found),
        ) % {"count": len(found)}
        context = {
            "recipient": user,
            "headline": subject,
            "suggestions": found,
            "site_url": settings.SITE_URL.rstrip("/"),
            "list_url": _absolute(reverse("suggestions:list")),
            "settings_url": _absolute(reverse("users:update")),
            "unsubscribe_url": _absolute(reverse("suggestions:unsubscribe", args=[make_unsubscribe_token(user)])),
        }
        text_body = render_to_string("suggestions/email/digest.txt", context)
        html_body = render_to_string("suggestions/email/digest.html", context)
    message = EmailMultiAlternatives(
        subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email],
        headers={"List-Unsubscribe": f"<{context['unsubscribe_url']}>"},
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)
    user.suggestions.filter(pk__in=[s.pk for s in pending]).update(emailed_at=now)
    return True


def send_suggestion_emails(now=None):
    """The weekly email to everyone who wants it and has something new. Returns how many
    were sent."""
    users = get_user_model().objects.filter(
        match_emails=True, is_active=True, suggestions__emailed_at=None, suggestions__dismissed_at=None,
    ).exclude(email="").distinct()
    return sum(1 for user in users if send_suggestion_email(user, now=now))
