from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

TOKEN_SALT    = "giving-volunteer-action"
TOKEN_MAX_AGE = 60 * 60 * 24 * 30   # 30 days


def make_action_token(request_pk, action):
    return signing.dumps({"id": request_pk, "action": action}, salt=TOKEN_SALT)


def read_action_token(token):
    return signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)


def _absolute(http_request, path):
    return http_request.build_absolute_uri(path)


def send_volunteer_request_email(vr, http_request):
    recipient = vr.recipient
    if not recipient or not recipient.email:
        return

    context = {
        "vr":          vr,
        "recipient":   recipient,
        "accept_url":  _absolute(http_request, reverse("giving:email_action", args=[make_action_token(vr.pk, "accept")])),
        "decline_url": _absolute(http_request, reverse("giving:email_action", args=[make_action_token(vr.pk, "decline")])),
        "detail_url":  _absolute(http_request, vr.get_absolute_url()),
    }
    subject = str(_("Volunteer stay request at %(c)s") % {"c": vr.community.name})
    _send(subject, recipient.email, "giving/email/volunteer_request", context)


def send_volunteer_response_email(vr, http_request):
    requester = vr.from_user
    if not requester or not requester.email:
        return

    status_label = _("accepted") if vr.status == "accepted" else _("declined")
    context = {
        "vr":         vr,
        "recipient":  requester,
        "status_label": status_label,
        "detail_url": _absolute(http_request, vr.get_absolute_url()),
    }
    subject = str(_("Your volunteer request at %(c)s has been %(status)s") % {
        "c": vr.community.name, "status": status_label,
    })
    _send(subject, requester.email, "giving/email/volunteer_response", context)


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
