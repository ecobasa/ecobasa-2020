"""What happened on a tour, at its stops, each with when it happened: who joined, who
gave or lent what it looked for, which hosts agreed, the gifts picked up and handed
over, and the references written afterwards. Followed while the tour goes on, read
once it is over."""

from datetime import datetime, timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Contribution, Match
from gift_economy.references.models import Reference, with_card_data
from gift_economy.references.reference_requests import exchange_dates

from .models import Delivery, Stop, Traveller

# What happened, as the timeline names it (tours/_timeline_entry.html)
PUBLISHED = "published"
JOINED = "joined"
GAVE = "gave"
LENT = "lent"
HELPED = "helped"
HOST_AGREED = "host_agreed"
PICKED_UP = "picked_up"
HANDED_OVER = "handed_over"
REFERENCE = "reference"
# What visitors see: nothing that names who travels, as people's profiles are for members
PUBLIC_KINDS = {HOST_AGREED, PICKED_UP, HANDED_OVER}


def timeline_by_stop(tour, stops, user):
    """The timeline at each stop, oldest first, in the order of `stops`: [[entry]], an
    entry being a dict with `kind`, `when`, `stop` and what it is about (`person`,
    `listing`, `host`, `to`, `reference`). Visitors see the hosts and the gifts, the
    group's references and those their authors shared: nothing else names who travels."""
    if not stops:
        return []
    entries = _happenings(tour, stops) + _references(tour, stops, user)
    if not user.is_authenticated:
        entries = [entry for entry in entries if entry["kind"] in PUBLIC_KINDS or entry["kind"] == REFERENCE]
    by_stop = {stop.pk: [] for stop in stops}
    for entry in sorted(entries, key=lambda entry: entry["when"]):
        by_stop[entry["stop"].pk].append(entry)
    return [by_stop[stop.pk] for stop in stops]


def _entry(kind, when, stop, **about):
    return {"kind": kind, "when": when, "stop": stop, **about}


def _happenings(tour, stops):
    by_pk = {stop.pk: stop for stop in stops}
    first = stops[0]
    entries = []
    if tour.published_at and tour.organiser_id:
        entries.append(_entry(PUBLISHED, tour.published_at, first, person=tour.organiser))
    # Who came along, where they got on, from when they were accepted
    for traveller in tour.counted_travellers():
        if traveller.match_id and traveller.match.responded_at:
            start, end = traveller.ends(stops)
            entries.append(_entry(
                JOINED, traveller.match.responded_at, by_pk.get(getattr(start, "pk", None), first),
                person=traveller.user, to=None if traveller.whole_route else end,
            ))
    # What it looked for and was given or lent, where the tour was when it was agreed
    for contribution in (
        Contribution.objects.filter(listing__tour=tour, listing__type=Listing.TYPE_WISH, match__status=Match.STATUS_ACCEPTED)
        .select_related("listing", "match__from_user", "match__content_type")
    ):
        match = contribution.match
        if match.responded_at:
            entries.append(_entry(
                _given(contribution.listing), match.responded_at, stop_on(timezone.localdate(match.responded_at), stops),
                person=match.from_user, listing=contribution.listing,
            ))
    # Hosts who agreed to take the group
    for stop in stops:
        match = stop.visit_match
        if match is not None and match.status == Match.STATUS_ACCEPTED and match.responded_at and not match.is_coming:
            entries.append(_entry(HOST_AGREED, match.responded_at, stop, host=stop.host))
    # The gifts that travelled along
    for delivery in tour.deliveries.filter(dismissed_at=None).select_related("offer", "wish", "bringer"):
        if delivery.picked_up_at:
            stop = by_pk.get(delivery.pickup_stop_id) or stop_on(timezone.localdate(delivery.picked_up_at), stops)
            entries.append(_entry(PICKED_UP, delivery.picked_up_at, stop, person=delivery.bringer, listing=delivery.offer))
        if delivery.delivered_at:
            stop = by_pk.get(delivery.dropoff_stop_id) or stop_on(timezone.localdate(delivery.delivered_at), stops)
            entries.append(_entry(
                HANDED_OVER, delivery.delivered_at, stop, person=delivery.bringer, listing=delivery.offer,
                to=delivery.wish.holder_name,
            ))
    return entries


def _given(need):
    if need.lend:
        return LENT
    return GAVE if need.is_thing else HELPED


def tour_match_ids(tour, stops):
    """The matches that are part of the tour: its tour visits, who travels along, the gifts
    that travel along, and what helped with its needs."""
    ids = {stop.visit_match_id for stop in stops if stop.visit_match_id}
    ids |= set(tour.travellers.exclude(match=None).values_list("match_id", flat=True))
    for pickup, handover in tour.deliveries.values_list("pickup_match_id", "handover_match_id"):
        ids |= {pickup, handover} - {None}
    needs = list(tour.listings.values_list("pk", flat=True))
    ids |= set(Contribution.objects.filter(listing__in=needs).values_list("match_id", flat=True))
    ids |= set(Match.objects.filter(
        content_type=ContentType.objects.get_for_model(Listing), object_id__in=[str(pk) for pk in needs],
    ).values_list("pk", flat=True))
    return ids


def _references(tour, stops, user):
    """The references written after what happened on the tour, and those about the group."""
    tour_type = ContentType.objects.get_for_model(tour)
    about_group = Q(content_type=tour_type, object_id=str(tour.pk))
    references = Reference.objects.filter(Q(match_id__in=tour_match_ids(tour, stops)) | about_group)
    if not user.is_authenticated:
        # The group's are on its page for everyone; about people only what was shared
        references = references.filter(about_group | Q(share_publicly=True))
    # A guestbook entry waiting for confirmation: for its author and who confirms it
    confirms = tour.can_confirm_references(user) if user.is_authenticated else False
    if not confirms:
        references = references.filter(Q(pending=False) | Q(author=user.pk))
    entries = []
    for reference in with_card_data(references):
        reference.can_confirm_entry = confirms and reference.pending
        # Who or what it is about, as its main tag; the kind of exchange for the group
        reference.about_other = reference.content_type_id != tour_type.pk
        reference.visible_skill_tags = reference.confirmed_skill_tags()
        entries.append(_entry(REFERENCE, reference.created_at, stop_of(reference, stops), reference=reference))
    return entries


def stop_of(reference, stops):
    """Where it happened: the stop its author named, the stop of the tour visit, where a
    gift was picked up or handed over, where a traveller got off; else the stop the tour
    had reached on the day it happened, or when it was written."""
    by_pk = {str(stop.pk): stop for stop in stops}
    if reference.place_type_id == ContentType.objects.get_for_model(Stop).pk and reference.place_id in by_pk:
        return by_pk[reference.place_id]
    by_pk = {stop.pk: stop for stop in stops}
    match = reference.match
    day = None
    if match is not None:
        for attachment in match.attachments():
            stop = _attachment_stop(attachment, match, stops)
            if stop is not None and stop.pk in by_pk:
                return by_pk[stop.pk]
        day = _day_of(match)
    return stop_on(day or timezone.localdate(reference.created_at), stops)


def _attachment_stop(attachment, match, stops):
    if isinstance(attachment, Stop):
        return attachment
    if isinstance(attachment, Delivery):
        return attachment.pickup_stop if match.pk == attachment.pickup_match_id else attachment.dropoff_stop
    if isinstance(attachment, Traveller):
        return attachment.ends(stops)[1]
    return None


def _day_of(match):
    """The day what the match is about happened (it ended, for a stay or a loan: the
    references come after it)."""
    for attachment in match.attachments():
        if hasattr(attachment, "happened_at"):
            when = attachment.happened_at(match)
            return timezone.localdate(when) if when else None
    start, end = exchange_dates(match)
    if isinstance(end, datetime):
        # Its end is the moment after it (a loan's: the next day's start)
        end -= timedelta(seconds=1)
    when = end or start
    return timezone.localdate(when) if isinstance(when, datetime) else when


def stop_on(day, stops):
    """The last stop the tour had reached by `day`, else its first."""
    found = stops[0]
    for stop in stops:
        arrived = stop.arrive_on or stop.leave_on
        if arrived and arrived <= day:
            found = stop
    return found
