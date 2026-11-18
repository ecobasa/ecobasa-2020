"""What happens to events, for add-ons of a kind to act on (events itself sends no
kind's emails)."""

from django.dispatch import Signal

# An event was created through its form: event, user (who created it)
event_created = Signal()

# Someone said "I'm coming": event, user, match
coming = Signal()
