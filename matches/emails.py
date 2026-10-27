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

from .models import Match

TOKEN_SALT    = "matches-action"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30   # 30 days


def make_action_token(match_pk, action):
    """Create a signed token encoding a Match pk + action."""
    return signing.dumps({"id": match_pk, "action": action}, salt=TOKEN_SALT)


def read_action_token(token):
    return signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)


def _absolute(http_request, path):
    return http_request.build_absolute_uri(path)


def _action_url(http_request, match_pk, action):
    token = make_action_token(match_pk, action)
    return _absolute(http_request, reverse("matches:email_action", args=[token]))


# ── Notification + email orchestration ─────────────────────────────────────────

def _notification(match, recipient, actor, tag):
    from notifications.models import Notification
    return Notification(recipient=recipient, actor=actor, match=match, tag=tag, link=match.get_absolute_url())


def _notify(match, recipient, actor, tag):
    """Create an in-app notification. Its text is built per reader at display time;
    `verb` only keeps a creation-time copy as a fallback."""
    notification = _notification(match, recipient, actor, tag)
    notification.verb = notification.text[:255]
    notification.save()
    return notification


def _other_party(match, user):
    return match.from_user if user == match.recipient else match.recipient


def notify_match_created(match, http_request=None):
    """In-app notification (+ email, if a request is available) to the recipient."""
    from notifications.models import Notification

    if match.recipient is None:
        return
    notification = _notify(match, match.recipient, match.from_user, Notification.TAG_REQUESTED)

    if http_request:
        _send_email(notification, "matches/email/match_request", http_request, {
            "accept_url":  _action_url(http_request, match.pk, "accept"),
            "decline_url": _action_url(http_request, match.pk, "decline"),
        })


def notify_match_response(match, actor, http_request=None, message="", counter=None):
    """In-app notification (+ email, if a request is available) to whichever party
    didn't just act. `message` is the note sent along with the decision, if any;
    `counter` is the MatchMessage holding a counter-proposal's details."""
    from notifications.models import Notification

    recipient = _other_party(match, actor)
    if recipient is None:
        return

    tag_map = {
        Match.STATUS_ACCEPTED: Notification.TAG_ACCEPTED,
        Match.STATUS_DECLINED: Notification.TAG_DECLINED,
        Match.STATUS_COUNTER:  Notification.TAG_COUNTER,
    }
    notification = _notify(match, recipient, actor, tag_map.get(match.status, ""))

    if http_request:
        _send_email(notification, "matches/email/match_response", http_request, {"message": message, "counter": counter})


def notify_match_message(match, sender, message, http_request=None):
    """In-app notification (+ email, if a request is available) to the other party
    about a new message in the match. Every message is emailed, but while an earlier
    message notification is still unread it is moved to the top instead of piling up
    a new one per message."""
    from django.utils import timezone
    from notifications.models import Notification

    recipient = _other_party(match, sender)
    if recipient is None:
        return

    bumped = Notification.objects.filter(
        recipient=recipient, match=match, tag=Notification.TAG_MESSAGE, is_read=False,
    ).update(actor=sender, created_at=timezone.now())
    if not bumped:
        _notify(match, recipient, sender, Notification.TAG_MESSAGE)

    if http_request:
        notification = _notification(match, recipient, sender, Notification.TAG_MESSAGE)
        _send_email(notification, "matches/email/match_message", http_request, {"message": message})


# ── Email sending ───────────────────────────────────────────────────────────────

def _send_email(notification, template_base, http_request, extra_context):
    """Email the notification's recipient, in their own language. The headline is the
    same sentence the in-app notification shows."""
    from django.conf import settings as conf
    from django.utils import translation

    recipient = notification.recipient
    if not recipient.email:
        return
    with translation.override(recipient.language or conf.LANGUAGE_CODE):
        headline = notification.text
        context = {
            "match":      notification.match,
            "recipient":  recipient,
            "headline":   headline,
            "detail_url": _absolute(http_request, notification.match.get_absolute_url()),
            **extra_context,
        }
        text_body = render_to_string(f"{template_base}.txt", context)
        html_body = render_to_string(f"{template_base}.html", context)
    msg = EmailMultiAlternatives(
        subject=headline,
        body=text_body,
        from_email=conf.DEFAULT_FROM_EMAIL,
        to=[recipient.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)


# ── Suggestions: what fits, found by the matching (matching.py) ───────────────

def notify_new_suggestions(users):
    """Tell each user about their new suggestions in the notifications: one notification
    that counts what's new, moved back to the top rather than piling up while unread."""
    from notifications.models import Notification

    for user in users:
        bumped = Notification.objects.filter(
            recipient=user, tag=Notification.TAG_SUGGESTION, is_read=False,
        ).update(created_at=timezone.now())
        if not bumped:
            notification = Notification(recipient=user, tag=Notification.TAG_SUGGESTION, link=reverse("matches:list"))
            notification.verb = notification.text[:255]
            notification.save()


# The weekly email with the new suggestions, for everyone who wants it: who has wishes hears
# about offers and skills nearby, who offers or has skills hears about wishes and projects.
# Sent by `send_suggestion_emails` (weekly cron); at most one a week per person.

SUGGESTIONS_UNSUBSCRIBE_SALT = "suggestions-unsubscribe"
SUGGESTIONS_MIN_INTERVAL = timedelta(days=6)


def make_suggestions_unsubscribe_token(user):
    return signing.dumps(user.pk, salt=SUGGESTIONS_UNSUBSCRIBE_SALT)


def read_suggestions_unsubscribe_token(token):
    return signing.loads(token, salt=SUGGESTIONS_UNSUBSCRIBE_SALT)


def _site_url(path):
    """Absolute link outside a request (the weekly email is sent by a command)."""
    return settings.SITE_URL.rstrip("/") + path


def send_suggestion_email(user, now=None):
    """Email `user` the suggestions not emailed yet (and not dismissed), unless they had
    one less than a week ago. Returns whether an email was sent."""
    now = now or timezone.now()
    last = user.suggestions.aggregate(last=Max("emailed_at"))["last"]
    if last and now - last < SUGGESTIONS_MIN_INTERVAL:
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
            "%(count)s new suggestion near you", "%(count)s new suggestions near you", len(found),
        ) % {"count": len(found)}
        context = {
            "recipient": user,
            "headline": subject,
            "suggestions": found,
            "site_url": settings.SITE_URL.rstrip("/"),
            "list_url": _site_url(reverse("matches:list")),
            "settings_url": _site_url(reverse("users:update") + "#matches"),
            "unsubscribe_url": _site_url(reverse("matches:suggestions_unsubscribe", args=[make_suggestions_unsubscribe_token(user)])),
        }
        text_body = render_to_string("matches/email/suggestions.txt", context)
        html_body = render_to_string("matches/email/suggestions.html", context)
    message = EmailMultiAlternatives(
        subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email],
        headers={"List-Unsubscribe": f"<{context['unsubscribe_url']}>"},
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)
    user.suggestions.filter(pk__in=[s.pk for s in pending]).update(emailed_at=now)
    return True


def send_suggestion_emails(now=None):
    """The weekly email to everyone who wants it and has new suggestions. Returns how many
    were sent."""
    users = get_user_model().objects.filter(
        match_emails=True, is_active=True, suggestions__emailed_at=None, suggestions__dismissed_at=None,
    ).exclude(email="").distinct()
    return sum(1 for user in users if send_suggestion_email(user, now=now))
