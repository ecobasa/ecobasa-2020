from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext as _

from notifications.models import Notification


def _community(reference):
    """The community a reference is about (itself, or the community of its offer or wish), if any."""
    subject = reference.subject
    if reference.content_type.model == "community":
        return subject
    return getattr(subject, "community", None)


def notify_reference_created(reference, http_request=None, base_url=None):
    """Tell the person a new reference is about (or the ambassador, for a community or
    its skills), linking straight to it in their references dashboard. Also emailed in
    their language when a request or base URL is available to build absolute links."""
    recipient = reference.recipient
    if recipient is None or recipient == reference.author:
        return
    url = reverse("references:list")
    community = _community(reference)
    if community is not None:
        url = f"{url}?community={community.slug}"
    notification = Notification.objects.create(
        recipient=recipient,
        actor=reference.author,
        reference=reference,
        tag=Notification.TAG_REFERENCE,
        # Fallback only; the shown text is built in the reader's language
        verb=_("New reference"),
        link=f"{url}#reference-{reference.pk}",
    )
    if http_request is not None:
        _send_email(notification, community, http_request.build_absolute_uri(notification.link))
    elif base_url:
        _send_email(notification, community, base_url.rstrip("/") + notification.link)


def _send_email(notification, community, detail_url):
    from django.conf import settings
    from django.utils import translation

    recipient = notification.recipient
    if not recipient.email:
        return
    reference = notification.reference
    with translation.override(recipient.language or settings.LANGUAGE_CODE):
        headline = notification.text
        context = {
            "recipient": recipient,
            "headline": headline,
            "reference": reference,
            "skills": [t.skill.get_name() for t in reference.skill_tags.exclude(status="declined")],
            "community": community,
            "detail_url": detail_url,
        }
        text_body = render_to_string("references/email/reference_created.txt", context)
        html_body = render_to_string("references/email/reference_created.html", context)
    msg = EmailMultiAlternatives(
        subject=headline, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)
