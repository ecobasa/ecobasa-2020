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

def notify_match_created(match, http_request=None):
    """In-app notification (+ email, if a request is available) to the recipient."""
    from notifications.models import Notification

    recipient = match.recipient
    if recipient is None:
        return

    target = match.target
    verb_text = _("%(actor)s %(verb)s: %(title)s") % {
        "actor": match.from_user.name or match.from_user.email,
        "verb":  target.get_match_verb(),
        "title": target.get_match_display_name(),
    }
    Notification.objects.create(
        recipient=recipient, actor=match.from_user,
        verb=str(verb_text), link=match.get_absolute_url(), tag="requested",
    )

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
        Match.STATUS_ACCEPTED: "accepted",
        Match.STATUS_DECLINED: "declined",
        Match.STATUS_COUNTER:  "counter",
    }
    tag = tag_map.get(match.status, "")
    actor_name = actor.name or actor.email
    verb_text = _("%(actor)s %(status)s your interest in: %(title)s") % {
        "actor":  actor_name,
        "status": match.get_status_display().lower(),
        "title":  match.target.get_match_display_name(),
    }
    Notification.objects.create(
        recipient=recipient, actor=actor,
        verb=str(verb_text), link=match.get_absolute_url(), tag=tag,
    )

    if http_request:
        _send_response_email(match, actor, http_request)


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
