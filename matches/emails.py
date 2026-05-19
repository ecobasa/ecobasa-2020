from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

TOKEN_SALT    = "matches-action"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30   # 30 days


def make_action_token(request_type, request_pk, action):
    """Create a signed token encoding type + pk + action."""
    return signing.dumps({"type": request_type, "id": request_pk, "action": action}, salt=TOKEN_SALT)


def read_action_token(token):
    return signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)


def _absolute(http_request, path):
    return http_request.build_absolute_uri(path)


def _action_url(http_request, request_type, pk, action):
    token = make_action_token(request_type, pk, action)
    return _absolute(http_request, reverse("matches:email_action", args=[token]))


# ── Volunteer stay ────────────────────────────────────────────────────────────

def send_volunteer_request_email(vr, http_request):
    recipient = vr.recipient
    if not recipient or not recipient.email:
        return
    context = {
        "vr":          vr,
        "recipient":   recipient,
        "accept_url":  _action_url(http_request, "volunteer", vr.pk, "accept"),
        "decline_url": _action_url(http_request, "volunteer", vr.pk, "decline"),
        "detail_url":  _absolute(http_request, vr.get_absolute_url()),
    }
    subject = str(_("Volunteer stay request at %(c)s") % {"c": vr.community.name})
    _send(subject, recipient.email, "matches/email/volunteer_request", context)


def send_volunteer_response_email(vr, http_request):
    requester = vr.from_user
    if not requester or not requester.email:
        return
    status_label = _("accepted") if vr.status == "accepted" else _("declined")
    context = {
        "vr":           vr,
        "recipient":    requester,
        "status_label": status_label,
        "detail_url":   _absolute(http_request, vr.get_absolute_url()),
    }
    subject = str(_("Your volunteer request at %(c)s has been %(status)s") % {
        "c": vr.community.name, "status": status_label,
    })
    _send(subject, requester.email, "matches/email/volunteer_response", context)


# ── Ad / freemarket request ───────────────────────────────────────────────────

def send_ad_request_email(ad_request, http_request):
    """Initial email to the ad owner when a request arrives."""
    recipient = ad_request.ad.owner
    if not recipient or not recipient.email:
        return
    ad = ad_request.ad
    context = {
        "ar":          ad_request,
        "ad":          ad,
        "recipient":   recipient,
        "accept_url":  _action_url(http_request, "ad_request", ad_request.pk, "accept"),
        "decline_url": _action_url(http_request, "ad_request", ad_request.pk, "decline"),
        "detail_url":  _absolute(http_request, ad_request.get_absolute_url()),
    }
    if ad.type == "offer":
        subject = str(_("Gift request: %(title)s") % {"title": ad.title})
    else:
        subject = str(_("Wish fulfillment offer: %(title)s") % {"title": ad.title})
    _send(subject, recipient.email, "matches/email/ad_request", context)


def send_ad_response_email(ad_request, actor, http_request):
    """Status-change email to whichever party didn't just respond."""
    ad = ad_request.ad
    owner = ad.owner
    recipient = ad_request.from_user if actor == owner else owner
    if not recipient or not recipient.email:
        return
    status_label = ad_request.get_status_display().lower()
    context = {
        "ar":           ad_request,
        "ad":           ad,
        "actor":        actor,
        "recipient":    recipient,
        "status_label": status_label,
        "detail_url":   _absolute(http_request, ad_request.get_absolute_url()),
    }
    subject = str(_("Ad request %(status)s: %(title)s") % {"status": status_label, "title": ad.title})
    _send(subject, recipient.email, "matches/email/ad_response", context)


# ── Skill request ─────────────────────────────────────────────────────────────

def send_skill_request_email(skill_request, http_request):
    """Initial email to the skill holder when a request arrives."""
    if skill_request.user_skill:
        recipient  = skill_request.user_skill.user
        skill_name = skill_request.user_skill.skill.name
    else:
        recipient  = skill_request.community_skill.community.owner
        skill_name = skill_request.community_skill.skill.name
    if not recipient or not recipient.email:
        return
    context = {
        "sr":          skill_request,
        "skill_name":  skill_name,
        "recipient":   recipient,
        "accept_url":  _action_url(http_request, "skill_request", skill_request.pk, "accept"),
        "decline_url": _action_url(http_request, "skill_request", skill_request.pk, "decline"),
        "detail_url":  _absolute(http_request, skill_request.get_absolute_url()),
    }
    subject = str(_("Skill request: %(skill)s") % {"skill": skill_name})
    _send(subject, recipient.email, "matches/email/skill_request", context)


def send_skill_response_email(skill_request, actor, http_request):
    """Status-change email to whichever party didn't just respond."""
    if skill_request.user_skill:
        skill_name = skill_request.user_skill.skill.name
        owner      = skill_request.user_skill.user
    else:
        skill_name = skill_request.community_skill.skill.name
        owner      = skill_request.community_skill.community.owner
    recipient = skill_request.from_user if actor == owner else owner
    if not recipient or not recipient.email:
        return
    status_label = skill_request.get_status_display().lower()
    context = {
        "sr":           skill_request,
        "skill_name":   skill_name,
        "actor":        actor,
        "recipient":    recipient,
        "status_label": status_label,
        "detail_url":   _absolute(http_request, skill_request.get_absolute_url()),
    }
    subject = str(_("Skill request %(status)s: %(skill)s") % {"status": status_label, "skill": skill_name})
    _send(subject, recipient.email, "matches/email/skill_response", context)


# ── Shared send helper ────────────────────────────────────────────────────────

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
