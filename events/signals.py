"""What happens to events, for add-ons of a kind to act on (events itself sends no
kind's emails)."""

from django.dispatch import Signal

# An event was created through its form: event, user (who created it)
event_created = Signal()

# Someone comes: they said "I'm coming", or the host accepted their request. event, user,
# match, data (what they sent with "I'm coming", None when the host accepted)
coming = Signal()

# Someone asked to join: event, user, match, data (what they sent)
asked_to_join = Signal()
