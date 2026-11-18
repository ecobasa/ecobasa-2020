"""The emails of a gift-circle: to whoever invites to one (the facilitator card), to
whoever comes (how it goes), each with the calendar file; to a tour's travellers where it
invites to one; and to guests, who confirm their email first."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.text import slugify
from django.utils.translation import gettext as _, gettext_lazy, gettext_noop

from events.ics import ics

from .timings import timings


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def exact_place(event):
    """Its place by name, exactly: for who comes. Lazy online, so it is said in the
    recipient's language."""
    if event.is_online:
        return gettext_lazy("Online, as a video call.")
    return event.get_match_location()[1]


def _send(event, recipient, template, subject, place_name=None, calendar=True, **extra):
    """`recipient`: a user or a guest. Without `place_name` its place as a user may see it."""
    with translation.override(recipient.language or settings.LANGUAGE_CODE):
        if place_name is None:
            # Its exact place: the host and who comes may know it
            place_name = _("Online, as a video call.") if event.is_online else event.place_for(recipient)[0]
        else:
            place_name = str(place_name)
        context = {
            "event": event,
            "recipient": recipient,
            "place_name": place_name,
            "event_url": _absolute(event.get_absolute_url()),
            "print_url": _absolute(reverse("gift_circles:print", args=[event.slug])),
            "headline": _(subject) % {"title": event.title},
            "timings": timings(event),
            **extra,
        }
        text_body = render_to_string(f"gift_circles/email/{template}.txt", context)
        html_body = render_to_string(f"gift_circles/email/{template}.html", context)
        calendar = ics(event, place_name) if calendar and event.starts_on else None
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


def send_tour_invitation(event, traveller):
    """To a traveller on the tour where it invites to a gift-circle: come along. No
    calendar file yet, they haven't said they come."""
    _send(
        event, traveller, "tour_invitation", gettext_noop("Your tour invites to a gift-circle: %(title)s"),
        calendar=False, tour=event.host_tour,
    )


def _guest_urls(guest):
    return {
        "manage_url": _absolute(reverse("gift_circles:guest", args=[guest.event.slug, guest.token])),
        "account_url": _absolute(reverse("gift_circles:guest_account", args=[guest.event.slug, guest.token])),
    }


def send_guest_confirmation(guest):
    """To someone who signed up as a guest: confirm it's you. Short: nothing more goes to
    an address until it is confirmed."""
    event = guest.event
    _send(
        event, guest, "guest_confirm", gettext_noop("Please confirm: you're coming to %(title)s"),
        place_name=event.rough_place()[0] if not event.is_online else None, calendar=False,
        confirm_url=_absolute(reverse("gift_circles:guest_confirm", args=[event.slug, guest.token])),
    )


def send_guest_welcome(guest):
    """To a guest once confirmed: how a gift-circle goes, the karma rules, the link to
    change or leave and why an account helps."""
    _send(
        guest.event, guest, "guest_coming", gettext_noop("You're coming to %(title)s"),
        place_name=exact_place(guest.event), **_guest_urls(guest),
    )
