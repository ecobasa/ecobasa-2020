"""Guests who create an account: their sign-ups move to it."""

from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from gift_economy.matches.models import Match, StayDetails

from .models import Attendee, Guest

# The guest whose link led to "Create an account", until they are logged in
GUEST_SESSION_KEY = "gift_circles_guest"


def link_to_account(token, user):
    """The guest rows with the email of the guest whose link it is, if it is the
    account's: the link proves the email is theirs (registering doesn't). At gift-circles
    still ahead they come from now on as everyone does: an accepted "I'm coming", and
    what they said yes to. Returns the rows linked."""
    guest = Guest.objects.filter(token=token).first()
    if guest is None or guest.email.lower() != (user.email or "").lower():
        return []
    rows = list(Guest.objects.filter(email__iexact=guest.email, user=None, confirmed_at__isnull=False).select_related("event"))
    with transaction.atomic():
        for row in rows:
            event = row.event
            if event.is_current and not event.matches.filter(from_user=user).exclude(status__in=Match.CLOSED_STATUSES).exists():
                match = Match(
                    from_user=user, recipient=event.get_match_owner(), message="",
                    status=Match.STATUS_ACCEPTED, responded_at=timezone.now(),
                )
                match.target = event
                match.save()
                day = _day_start(event.starts_on)
                StayDetails.objects.create(
                    match=match, volunteer_mode=StayDetails.MODE_COME, people=row.people,
                    stay_from=day, stay_to=_day_start(event.ends_on) or day,
                )
            Attendee.objects.update_or_create(event=event, user=user, defaults={"keep_on_ecobasa": row.keep_on_ecobasa})
            row.user = user
            row.save(update_fields=["user"])
    return rows


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None
