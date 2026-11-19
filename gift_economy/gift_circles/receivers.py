"""Gift-circles listen to what happens to events: whoever invites to one and whoever
comes gets the instructions, once the request is saved; a tour's travellers are invited
to its own; what someone said yes to when coming is kept, and what others bring is
matched with theirs, and what is shared from afar at an online one with anyone's who can
share it from afar too. A guest who creates an account through their link brings their
sign-ups along."""

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.db import transaction
from django.dispatch import receiver
from django.utils import translation
from django.utils.translation import gettext as _

from events import kinds
from events.signals import asked_to_join, coming, event_created
from gift_economy.gifts.models import Listing

from .bringing import suggest_for_newcomer
from .emails import send_coming_confirmation, send_host_confirmation, send_tour_invitation
from .guests import GUEST_SESSION_KEY, link_to_account
from .models import Attendee
from .skill_sharing import schedule_share_with


@receiver(event_created)
def confirm_to_host(sender, event, user, **kwargs):
    if event.kind != kinds.GIFT_CIRCLE:
        return
    if user.email:
        transaction.on_commit(lambda: send_host_confirmation(event, user))
    if event.host_tour_id:
        transaction.on_commit(lambda: invite_travellers(event, user))


def invite_travellers(event, inviter):
    """The travellers at the stop where their tour invites to a gift-circle, but who
    invited: a notification and an email each."""
    from notifications.models import Notification

    tour = event.host_tour
    people = {}
    for stop in tour.stops.filter(event=event):
        for traveller in tour.present_at(stop):
            people[traveller.user_id] = traveller.user
    people.pop(inviter.pk, None)
    for person in people.values():
        with translation.override(person.language or settings.LANGUAGE_CODE):
            verb = _("%(tour)s invites to a gift-circle: %(title)s") % {"tour": tour.title, "title": event.title}
        Notification.objects.create(
            recipient=person, actor=inviter, verb=verb[:255], link=event.get_absolute_url(),
            tag=Notification.TAG_INVITATION,
        )
        if person.email:
            send_tour_invitation(event, person)


def _keep_answer(event, user, data):
    """Whether their offers and wishes from it stay on ecobasa, as they ticked it."""
    if data is not None:
        Attendee.objects.update_or_create(
            event=event, user=user, defaults={"keep_on_ecobasa": bool(data.get("keep_on_ecobasa"))},
        )


@receiver(coming)
def confirm_coming(sender, event, user, data=None, **kwargs):
    if event.kind != kinds.GIFT_CIRCLE:
        return
    _keep_answer(event, user, data)
    if user.email:
        transaction.on_commit(lambda: send_coming_confirmation(event, user))
    transaction.on_commit(lambda: suggest_for_newcomer(event, user))


@receiver(asked_to_join)
def remember_answer(sender, event, user, data=None, **kwargs):
    if event.kind == kinds.GIFT_CIRCLE:
        _keep_answer(event, user, data)


@receiver(user_logged_in)
def take_guest_rows_along(sender, request, user, **kwargs):
    """Logged in (or registered) after "Create an account" in a guest's link."""
    token = request.session.pop(GUEST_SESSION_KEY, None) if request is not None else None
    if token:
        link_to_account(token, user)


@receiver(post_save, sender=Listing)
def share_with_from_afar(sender, instance, raw=False, **kwargs):
    if not raw and instance.from_afar:
        schedule_share_with(instance)
