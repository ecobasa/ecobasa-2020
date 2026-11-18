"""The emails of a gift-circle: to whoever invites to one (the facilitator card) and to
whoever comes (how it goes), each with the calendar file."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.text import slugify
from django.utils.translation import gettext as _, gettext_noop

from events.ics import ics

from .timings import timings


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def _send(event, recipient, template, subject):
    with translation.override(recipient.language or settings.LANGUAGE_CODE):
        # Its exact place: the host and who comes may know it
        place_name = _("Online, as a video call.") if event.is_online else event.place_for(recipient)[0]
        context = {
            "event": event,
            "recipient": recipient,
            "place_name": place_name,
            "event_url": _absolute(event.get_absolute_url()),
            "print_url": _absolute(reverse("gift_circles:print", args=[event.slug])),
            "headline": _(subject) % {"title": event.title},
            "timings": timings(event),
        }
        text_body = render_to_string(f"gift_circles/email/{template}.txt", context)
        html_body = render_to_string(f"gift_circles/email/{template}.html", context)
        calendar = ics(event, place_name) if event.starts_on else None
    message = EmailMultiAlternatives(
        subject=context["headline"], body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient.email],
    )
    message.attach_alternative(html_body, "text/html")
    if calendar:
        message.attach(f"{slugify(event.title) or 'gift-circle'}.ics", calendar, "text/calendar")
    message.send(fail_silently=True)


def send_host_confirmation(event, host):
    """To whoever invited: everything for the day, the facilitator card first."""
    _send(event, host, "host", gettext_noop("Your gift-circle is on ecobasa: %(title)s"))


def send_coming_confirmation(event, person):
    """To someone with an account who comes: how a gift-circle goes and the karma rules."""
    _send(event, person, "coming", gettext_noop("You're coming to %(title)s"))
