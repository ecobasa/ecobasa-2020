"""The day before a gift-circle, everyone who comes and its host hear that it is
tomorrow: where and when, what of the others' fits their offers and wishes, and how to
add theirs. Sent by `send_gift_circle_reminders` once a day (see crontab): the circles of
tomorrow, so each one once."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_noop

from events import kinds
from events.models import Event

from . import bringing
from .emails import _guest_urls, _send, exact_place

SUBJECT = gettext_noop("Tomorrow: %(title)s")


def recipients(event):
    """(people with an account, guests) who come, the host first."""
    ids = bringing.coming_ids(event)
    manager = event.manager
    people = list(get_user_model().objects.filter(pk__in=ids - {manager.pk if manager else None}))
    if manager is not None:
        people.insert(0, manager)
    return [person for person in people if person.email], list(event.guests.coming())


def send_reminder(event, recipient, guest=False):
    offers, wishes = bringing.brought(event)
    extra = {"brought": bool(offers or wishes), "is_guest": guest}
    if guest:
        extra.update(_guest_urls(recipient))
    else:
        extra["is_host"] = recipient == event.manager
        extra["brings"] = any(listing.owner_id == recipient.pk for listing in offers + wishes)
        extra["suggestions"] = bringing.circle_suggestions(event, recipient)
    _send(
        event, recipient, "reminder", SUBJECT, place_name=exact_place(event), calendar=False, **extra,
    )
    for suggestion in extra.get("suggestions", ()):
        if suggestion.emailed_at is None:
            suggestion.emailed_at = timezone.now()
            suggestion.save(update_fields=["emailed_at"])


def send_reminders(today=None):
    """To everyone who comes to a gift-circle tomorrow. Returns how many emails went."""
    tomorrow = (today or timezone.localdate()) + timedelta(days=1)
    sent = 0
    circles = Event.objects.filter(kind=kinds.GIFT_CIRCLE, starts_on=tomorrow, archived_at=None).select_related(
        "community__ambassador", "host_user", "host_tour__organiser",
    )
    for event in circles:
        people, guests = recipients(event)
        for person in people:
            send_reminder(event, person)
        for guest in guests:
            send_reminder(event, guest, guest=True)
        sent += len(people) + len(guests)
    return sent
