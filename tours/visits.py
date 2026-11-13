"""Tour visits: a tour's stay at a stop's host, asked once for the whole group,
not once per traveller. The visit is an ordinary stay (`matches.create_stay`) with the stop attached
(`Stop.visit_match`): the host answers it like a volunteer stay, counts it in their
calendar, and its group sees the place once it is accepted (`StayDetails.companions`)."""

from datetime import datetime, time

from django.db import transaction
from django.utils import timezone
from django.utils.translation import ngettext

from gift_economy.matches.emails import notify_match_created, notify_match_message
from gift_economy.matches.models import Match, MatchMessage, StayDetails, create_stay

_OPEN = (Match.STATUS_PENDING, Match.STATUS_COUNTER, Match.STATUS_ACCEPTED)


def day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None


def _companions(group, asker):
    return {t.user_id for t in group} - {asker.pk}


def ask_host(stop, user, *, message="", stay_from=None, stay_to=None, contributions=(), practice_skills="",
             http_request=None):
    """Ask the stop's host to take the group, or, at an event where people just come,
    say the tour comes (accepted at once, nobody is asked)."""
    group = stop.group()
    coming = stop.joins_open_event
    with transaction.atomic():
        match = create_stay(
            user, stop.host, message=message, stay_from=day_start(stay_from), stay_to=day_start(stay_to),
            people=max(stop.group_people(group), 1), contributions=contributions,
            companions=_companions(group, user),
            practice_skills=practice_skills,
            volunteer_mode=StayDetails.MODE_COME if coming else "",
            status=Match.STATUS_ACCEPTED if coming else None,
        )
        stop.visit_match = match
        stop.save(update_fields=["visit_match"])
    if not coming:
        notify_match_created(match, http_request=http_request)
    return match


def sync_visits(tour):
    """Keep each open tour visit's people and companions in step with the travellers at
    its stop. An agreed group that changes is told to the host in the conversation."""
    for stop in tour.stops.select_related("visit_match__stay_details", "event", "community"):
        match = stop.visit_match
        if match is None or match.status not in _OPEN:
            continue
        details = match.stay_details
        group = stop.group()
        people = max(stop.group_people(group), 1)
        companions = _companions(group, match.from_user)
        if people == details.people and companions == set(details.companions.values_list("pk", flat=True)):
            continue
        details.people = people
        details.save(update_fields=["people"])
        details.companions.set(companions)
        if match.status == Match.STATUS_ACCEPTED and not match.is_coming:
            body = ngettext(
                "Our group has changed: we are %(n)s person now.",
                "Our group has changed: we are %(n)s people now.", people,
            ) % {"n": people}
            MatchMessage.objects.create(match=match, sender=match.from_user, body=body)
            notify_match_message(match, sender=match.from_user, message=body)


def follow_agreed_days(match):
    """A tour visit was accepted on other days (the host's or the organisers'
    counter-proposal): the stop takes them over."""
    stop = getattr(match, "tour_stop", None)
    if stop is None or match.status != Match.STATUS_ACCEPTED:
        return
    start, end = (timezone.localdate(value) if value else None for value in match.stay_period())
    if (start, end) == (stop.arrive_on, stop.leave_on) or not (start or end):
        return
    stop.arrive_on, stop.leave_on = start or stop.arrive_on, end or stop.leave_on
    stop.save(update_fields=["arrive_on", "leave_on"])
    details = match.stay_details
    details.stay_from, details.stay_to = day_start(stop.arrive_on), day_start(stop.leave_on)
    details.save(update_fields=["stay_from", "stay_to"])
    stop.tour.rebuild_route()


def clashes(stops):
    """Indices of the stops whose days overlap the stop before (after other days were
    agreed, say)."""
    found = set()
    for i in range(1, len(stops)):
        before, stop = stops[i - 1], stops[i]
        if before.leave_on and stop.arrive_on and stop.arrive_on < before.leave_on:
            found.add(i)
    return found

