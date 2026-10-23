from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

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

def _notify(match, recipient, actor, tag):
    """Create an in-app notification. Its text is built per reader at display time;
    `verb` only keeps a creation-time copy as a fallback."""
    from notifications.models import Notification

    notification = Notification(
        recipient=recipient, actor=actor, match=match, tag=tag, link=match.get_absolute_url(),
    )
    notification.verb = notification.text[:255]
    notification.save()
    return notification


def notify_match_created(match, http_request=None):
    """In-app notification (+ email, if a request is available) to the recipient."""
    from notifications.models import Notification

    if match.recipient is None:
        return
    _notify(match, match.recipient, match.from_user, Notification.TAG_REQUESTED)

    if http_request:
        _send_request_email(match, http_request)


def notify_match_response(match, actor, http_request=None):
    """In-app notification (+ email, if a request is available) to whichever party
    didn't just act."""
    from notifications.models import Notification

    recipient = match.from_user if actor == match.recipient else match.recipient
    if recipient is None:
        return

    tag_map = {
        Match.STATUS_ACCEPTED: Notification.TAG_ACCEPTED,
        Match.STATUS_DECLINED: Notification.TAG_DECLINED,
        Match.STATUS_COUNTER:  Notification.TAG_COUNTER,
    }
    _notify(match, recipient, actor, tag_map.get(match.status, ""))

    if http_request:
        _send_response_email(match, actor, http_request)


def notify_match_message(match, sender):
    """In-app notification to the other party about a new message in the match.
    While an earlier message notification is still unread, it is moved to the top
    instead of piling up a new one per message."""
    from django.utils import timezone
    from notifications.models import Notification

    recipient = match.from_user if sender == match.recipient else match.recipient
    if recipient is None:
        return

    bumped = Notification.objects.filter(
        recipient=recipient, match=match, tag=Notification.TAG_MESSAGE, is_read=False,
    ).update(actor=sender, created_at=timezone.now())
    if not bumped:
        _notify(match, recipient, sender, Notification.TAG_MESSAGE)


# ── Email sending ───────────────────────────────────────────────────────────────

def _send_request_email(match, http_request):
    recipient = match.recipient
    if not recipient or not recipient.email:
        return
    target = match.target
    verb = target.get_match_verb()
    title = target.get_match_display_name()
    context = {
        "match":       match,
        "recipient":   recipient,
        "title":       title,
        "verb":        verb,
        "accept_url":  _action_url(http_request, match.pk, "accept"),
        "decline_url": _action_url(http_request, match.pk, "decline"),
        "detail_url":  _absolute(http_request, match.get_absolute_url()),
    }
    subject = str(_("%(verb)s: %(title)s") % {"verb": verb.capitalize(), "title": title})
    _send(subject, recipient.email, "matches/email/match_request", context)


def _send_response_email(match, actor, http_request):
    recipient = match.from_user if actor == match.recipient else match.recipient
    if not recipient or not recipient.email:
        return
    title = match.target.get_match_display_name()
    status_label = match.get_status_display().lower()
    context = {
        "match":        match,
        "actor":        actor,
        "recipient":    recipient,
        "title":        title,
        "status_label": status_label,
        "detail_url":   _absolute(http_request, match.get_absolute_url()),
    }
    subject = str(_("%(status)s: %(title)s") % {"status": status_label.capitalize(), "title": title})
    _send(subject, recipient.email, "matches/email/match_response", context)


def _send(subject, to_email, template_base, context):
    from django.conf import settings as conf
    text_body = render_to_string(f"{template_base}.txt", context)
    html_body = render_to_string(f"{template_base}.html", context)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=conf.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)
