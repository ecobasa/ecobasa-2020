"""Gift-circles listen to what happens to events: whoever invites to one and whoever
comes gets the instructions, once the request is saved; a new one invites its host's
members or travellers and who lives nearby, as its host ticked it; what someone said yes to when coming is kept, and what others bring is
matched with theirs, and what is shared from afar at an online one with anyone's who can
share it from afar too. A guest who creates an account through their link brings their
sign-ups along."""

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models import Q
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
from .invitations import invite, suggest_nearby
from .models import Attendee
from .skill_sharing import schedule_share_with


@receiver(event_created)
def confirm_to_host(sender, event, user, data=None, **kwargs):
    if event.kind != kinds.GIFT_CIRCLE:
        return
    if user.email:
        transaction.on_commit(lambda: send_host_confirmation(event, user))
    data = data or {}
    transaction.on_commit(lambda: invite_new(event, user, data.get("invite_members"), data.get("invite_nearby")))


def invite_new(event, host, members, nearby):
    """As its host ticked it on a new gift-circle: its community's members or its tour's
    travellers are invited, and who lives nearby gets it as a suggestion."""
    invited = set()
    if members and event.host_tour_id:
        invited = invite_travellers(event, host)
    elif members and event.community_id:
        people = [person for person in event.community.members() if person.is_active]
        invited = {invitation.user_id for invitation in invite(event, host, people, [], "")}
    if nearby:
        suggest_nearby(event, host, exclude=invited)


def invite_travellers(event, inviter):
    """The travellers at the stop where their tour invites to a gift-circle (all of them
    if it is at none), but who invited: a notification and an email each. Returns their
    ids."""
    from notifications.models import Notification

    tour = event.host_tour
    people = {}
    stops = tour.stops.filter(Q(event=event) | Q(gift_circle=event))
    for stop in stops:
        for traveller in tour.present_at(stop):
            people[traveller.user_id] = traveller.user
    if not stops:
        people = {traveller.user_id: traveller.user for traveller in tour.counted_travellers()}
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
    return set(people)


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
