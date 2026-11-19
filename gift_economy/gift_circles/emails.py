"""The emails of a gift-circle: to whoever invites to one (the facilitator card), to
whoever comes (how it goes), each with the calendar file; to a tour's travellers where it
invites to one, and to people invited to one; and to guests, who confirm their email
first."""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.text import slugify
from django.utils.translation import gettext as _, gettext_lazy, gettext_noop

from events.ics import ics

from .models import Guest
from .timings import timings


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def exact_place(event):
    """Its place by name, exactly: for who comes. Lazy online, so it is said in the
    recipient's language."""
    if event.is_online:
        return gettext_lazy("Online, as a video call.")
    return event.get_match_location()[1]


def video_call_url(event, recipient):
    """Online, the page of its video call on ecobasa: a guest's through their link."""
    if not event.is_online:
        return ""
    if isinstance(recipient, Guest):
        return _absolute(reverse("gift_circles:guest_video_call", args=[event.slug, recipient.token]))
    return _absolute(reverse("gift_circles:video_call", args=[event.slug]))


def _send(event, recipient, template, subject, place_name=None, calendar=True, subject_args=None, reply_to=None, **extra):
    """`recipient`: a user, a guest or an invitation by email. Without `place_name` its
    place as a user may see it. Online, the calendar file's place is its video call."""
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
            "help_url": _absolute(reverse("help:gift_circles")),
            "headline": _(subject) % {"title": event.title, **(subject_args or {})},
            "timings": timings(event),
            "video_call_url": video_call_url(event, recipient),
            **extra,
        }
        text_body = render_to_string(f"gift_circles/email/{template}.txt", context)
        html_body = render_to_string(f"gift_circles/email/{template}.html", context)
        calendar = ics(event, context["video_call_url"] or place_name) if calendar and event.starts_on else None
    message = EmailMultiAlternatives(
        subject=context["headline"], body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient.email],
        reply_to=reply_to,
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


def send_member_invitation(invitation, message):
    """To a member invited by name: what a gift-circle is, and "I'm coming"."""
    _send(
        invitation.event, invitation.user, "invitation", gettext_noop("%(name)s invites you to a gift-circle: %(title)s"),
        calendar=False, subject_args={"name": invitation.inviter_name()}, invitation=invitation, message=message,
    )


def send_email_invitation(invitation, message):
    """To an address someone invited: what a gift-circle is, coming as a guest, and where
    to say they don't come, which deletes the address. Its place roughly: they don't come
    yet."""
    event = invitation.event
    _send(
        event, invitation, "invitation", gettext_noop("%(name)s invites you to a gift-circle: %(title)s"),
        place_name=None if event.is_online else event.rough_place()[0], calendar=False,
        subject_args={"name": invitation.inviter_name()}, invitation=invitation, message=message,
        answer_url=_absolute(reverse("gift_circles:invitation", args=[event.slug, invitation.token])),
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


def send_written(entry, sender_name, sender_email, recipient, message):
    """"Write to them": a few words to the other side of a line, without their address;
    answering goes to the sender."""
    event = entry.event
    _send(
        event, recipient, "write", gettext_noop("%(name)s writes to you from the gift-circle %(title)s"),
        place_name="", calendar=False, subject_args={"name": sender_name}, reply_to=[sender_email],
        entry=entry, sender_name=sender_name, message=message,
    )
