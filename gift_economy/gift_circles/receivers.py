"""Gift-circles listen to what happens to events: whoever invites to one and whoever
comes gets the instructions, once the request is saved."""

from django.db import transaction
from django.dispatch import receiver

from events import kinds
from events.signals import coming, event_created

from .emails import send_coming_confirmation, send_host_confirmation


@receiver(event_created)
def confirm_to_host(sender, event, user, **kwargs):
    if event.kind == kinds.GIFT_CIRCLE and user.email:
        transaction.on_commit(lambda: send_host_confirmation(event, user))


@receiver(coming)
def confirm_coming(sender, event, user, **kwargs):
    if event.kind == kinds.GIFT_CIRCLE and user.email:
        transaction.on_commit(lambda: send_coming_confirmation(event, user))
