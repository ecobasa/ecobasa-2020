"""Gifts that travel along a tour: an offer at or near one place on the route fits a
wish at or near a later one, and a traveller who is on the tour in between takes it
along. That is how gifts cross distances nobody would drive for a bag of seeds.

What is looked at, things only (skills don't travel) and nothing to lend (it comes
back):
- the hosts' offers (a community's, also at one of its events) against the later hosts'
  wishes and their events' needs;
- the travellers' own offers, which travel with them from where they get on, against
  the hosts' wishes and the wishes of people living near the route;
- on the way: offers of people and public goods near the route, picked up between two
  stops, against wishes later on.

Whether an offer fits a wish is the general matching (gift_economy.matches.matching.fit),
seeds only where they grow, but without a distance limit: the tour is the bridge.

A place on the route is a position: stop i is i, a place near the leg from stop i to the
next is i and how far along that leg it is. A pair is suggested only in route order,
and only to travellers who are on the tour from where it is picked up until where it is
handed over. A vehicle a traveller offers in the gifts is a gift to give away like any
other: it is suggested only when someone along the route wishes for one.

Taking a pair up (take) makes a Delivery with two ordinary matches: the bringer asks
the giver for the offer, and offers it to the one who wishes for it."""

from dataclasses import dataclass, field

from django.contrib.gis.geos import LineString
from django.contrib.gis.measure import D
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from gift_economy.gifts.models import Listing
from gift_economy.matches.emails import notify_match_created, notify_match_response
from gift_economy.matches.matching import fit, km_to_route, side_of
from gift_economy.matches.models import Contribution, Match, MatchMessage

from .models import Delivery
from .visits import day_start

# People and public goods this close to the route are on the way
NEAR_ROUTE_KM = 15


@dataclass
class Spot:
    """Where on the route a gift is picked up or handed over."""

    position: float
    stop: object = None  # None: on the way, near the route between two stops
    label: str = ""

    @property
    def day(self):
        """The day the tour is there, if known."""
        if self.stop is None:
            return None
        return self.stop.arrive_on or self.stop.leave_on


@dataclass
class Pair:
    """An offer that could travel along to a wish, and who could take it."""

    offer: Listing
    wish: Listing
    pickup: Spot
    dropoff: Spot
    reason: str
    quantity: int | None
    # The bringer's own offer, which travels with them
    own: bool = False
    bringers: list = field(default_factory=list)

    @property
    def key(self):
        return f"{self.offer.pk}:{self.wish.pk}"

    @property
    def amount(self):
        return self.wish.format_amount(self.quantity) if self.quantity else ""

    @property
    def needs_pickup(self):
        return not (self.own or self.offer.public_good)

    def asks_giver(self, user):
        """Whether taking it asks the giver: not for one's own, a public good, or what
        one answers for (a community's gift its ambassador takes along)."""
        return self.needs_pickup and self.offer.manager != user

    def can_take(self, user):
        return user.is_authenticated and user.pk in self.bringers


def _things():
    return (
        Listing.objects.current().things().exclude(lend=True)
        .select_related("owner", "community__ambassador", "event__community", "thing")
        .prefetch_related("contributions__match")
    )


def _at(stop, listing):
    """Whether a host's listing is at the stop: the community's own, and its event's
    needs at a stop at the event (at a stay with the community, all its events')."""
    if listing.community_id != stop.community_id:
        return False
    return listing.event_id is None or stop.event_id is None or listing.event_id == stop.event_id


def _legs(stops):
    """(index, line) for each leg between two stops that are on the map."""
    points = [(i, stop.public_place()[1]) for i, stop in enumerate(stops)]
    points = [(i, point) for i, point in points if point is not None]
    return [(i, LineString(a.coords, b.coords, srid=4326)) for (i, a), (_j, b) in zip(points, points[1:])]


def _on_the_way(point, legs):
    """The position of a place near the route, or None if it isn't near it."""
    best = None
    for i, line in legs:
        km = km_to_route(point, line)
        if km <= NEAR_ROUTE_KM and (best is None or km < best[0]):
            best = (km, i + line.project_normalized(point))
    return None if best is None else best[1]


def _near_route(tour, type, legs, exclude_owners):
    """People's things of `type` near the route (their own place or where they live),
    with their position on it."""
    if tour.route is None or not legs:
        return []
    near = D(km=NEAR_ROUTE_KM)
    candidates = _things().filter(type=type, owner__isnull=False, community=None, tour=None).exclude(
        owner__in=exclude_owners,
    ).filter(
        Q(location__dwithin=(tour.route, near)) | Q(location=None, owner__location__dwithin=(tour.route, near))
    )
    found = []
    for listing in candidates:
        position = _on_the_way(listing.point, legs)
        if position is not None:
            found.append((listing, [Spot(position, None, listing.public_place[0] or listing.holder_name)]))
    return found


def _spans(tour, stops):
    """{user id: (first, last position)} of the counted travellers."""
    index = {stop.pk: i for i, stop in enumerate(stops)}
    return {
        traveller.user_id: (index.get(traveller.from_stop_id, 0), index.get(traveller.to_stop_id, len(stops) - 1))
        for traveller in tour.counted_travellers()
    }


def _quantity(offer, wish):
    """How much could travel, in the wish's unit: what is still missing, at most what is
    left of the offer if it counts the same way."""
    want, have = wish.remaining, offer.remaining if offer.unit == wish.unit else None
    if want is None:
        return have
    return want if have is None else min(want, have)


def delivery_suggestions(tour, stops=None):
    """What could travel along the tour, as Pairs in route order. Not what was taken up
    or set aside already, and only what someone on the tour can take."""
    stops = tour.ordered_stops() if stops is None else stops
    if len(stops) < 2:
        return []
    spans = _spans(tour, stops)
    legs = _legs(stops)
    hosts = [(i, stop) for i, stop in enumerate(stops) if stop.community_id]

    def host_listings(type):
        listings = _things().filter(type=type, community__in={stop.community_id for _i, stop in hosts})
        found = []
        for listing in listings:
            spots = [Spot(i, stop, stop.label) for i, stop in hosts if _at(stop, listing)]
            if spots:
                found.append((listing, spots))
        return found

    travellers = set(spans)
    # Their own: with them from where they get on, before anything there is picked up
    own = [
        (listing, [Spot(spans[listing.owner_id][0] - 0.5, None, "")])
        for listing in _things().filter(
            type=Listing.TYPE_OFFER, owner__in=travellers, community=None, tour=None, public_good=False,
        )
    ]
    offers = host_listings(Listing.TYPE_OFFER) + own + _near_route(tour, Listing.TYPE_OFFER, legs, travellers)
    wishes = host_listings(Listing.TYPE_WISH) + _near_route(tour, Listing.TYPE_WISH, legs, travellers)

    taken = {f"{offer}:{wish}" for offer, wish in tour.deliveries.values_list("offer_id", "wish_id")}
    own_ids = {listing.pk for listing, _spots in own}
    sides = {}

    def side(listing):
        if listing.pk not in sides:
            sides[listing.pk] = side_of(listing)
        return sides[listing.pk]

    pairs = []
    for offer, pickups in offers:
        offer_side = side(offer)
        if offer_side is None:
            continue
        for wish, dropoffs in wishes:
            if f"{offer.pk}:{wish.pk}" in taken:
                continue
            wish_side = side(wish)
            if wish_side is None or wish_side.owner == offer_side.owner:
                continue
            reason = fit(offer_side, wish_side)
            if reason is None:
                continue
            # The first place it can be picked up, and the first after it to hand it over
            ends = next(
                ((a, b) for a in sorted(pickups, key=lambda s: s.position)
                 for b in sorted(dropoffs, key=lambda s: s.position) if a.position < b.position),
                None,
            )
            if ends is None:
                continue
            pickup, dropoff = ends
            is_own = offer.pk in own_ids
            if is_own:
                first, last = spans[offer.owner_id]
                bringers = [offer.owner_id] if dropoff.position <= last else []
            else:
                bringers = [
                    user for user, (first, last) in spans.items()
                    if first <= pickup.position and dropoff.position <= last
                ]
            if not bringers:
                continue
            pairs.append(Pair(offer, wish, pickup, dropoff, reason, _quantity(offer, wish), own=is_own, bringers=bringers))
    pairs.sort(key=lambda pair: (pair.pickup.position, pair.dropoff.position, pair.offer.display_title.lower()))
    return pairs


def find(tour, key):
    """The suggested pair for "offer:wish", or None if it isn't suggested (any more)."""
    return next((pair for pair in delivery_suggestions(tour) if pair.key == key), None)


# ── Taking it up ───────────────────────────────────────────────────

def _day_text(day):
    return date_format(day, "D j M") if day else ""


def default_messages(tour, pair):
    """(to the giver, to the receiver): ready-made messages the bringer can change."""
    title = f"{pair.offer.display_title} ({pair.amount})" if pair.amount else pair.offer.display_title
    where = pair.dropoff.label or pair.wish.holder_name
    to_giver = _("Hello! I'm travelling with the tour %(tour)s and could take %(title)s along to %(where)s, where it is wished for.") % {
        "tour": tour.title, "title": title, "where": where,
    }
    if pair.pickup.day:
        to_giver += " " + _("We are with you around %(day)s.") % {"day": _day_text(pair.pickup.day)}
    origin = pair.pickup.label or pair.offer.holder_name
    to_receiver = _("Hello! I'm travelling with the tour %(tour)s and could bring you %(title)s from %(origin)s.") % {
        "tour": tour.title, "title": title, "origin": origin,
    } if pair.needs_pickup else _("Hello! I'm travelling with the tour %(tour)s and could bring you %(title)s.") % {
        "tour": tour.title, "title": title,
    }
    if pair.dropoff.day:
        to_receiver += " " + _("We are with you around %(day)s.") % {"day": _day_text(pair.dropoff.day)}
    return to_giver, to_receiver


def _ask(user, listing, message, spot, contributions):
    match = Match(from_user=user, recipient=listing.get_match_owner(), message=message, proposed_date=day_start(spot.day))
    match.target = listing
    match.save()
    Contribution.objects.bulk_create([
        Contribution(match=match, listing=item, quantity=quantity) for item, quantity in contributions
    ])
    return match


def take(tour, pair, user, quantity=None, to_giver="", to_receiver="", http_request=None):
    """The bringer takes a pair up: a match asking the giver for the offer (none for
    their own offer or a public good), one offering it to the one who wishes for it,
    with the stop's days and how much, and the Delivery that links them."""
    quantity = pair.quantity if quantity is None else quantity
    offer_quantity = quantity if pair.offer.unit == pair.wish.unit else None
    with transaction.atomic():
        pickup = None
        if pair.asks_giver(user):
            pickup = _ask(user, pair.offer, to_giver, pair.pickup, [(pair.offer, offer_quantity)])
        gives = [(pair.wish, quantity)] + ([(pair.offer, offer_quantity)] if pair.own else [])
        handover = _ask(user, pair.wish, to_receiver, pair.dropoff, gives)
        delivery = Delivery.objects.create(
            tour=tour, offer=pair.offer, wish=pair.wish, quantity=quantity, bringer=user,
            pickup_stop=pair.pickup.stop, dropoff_stop=pair.dropoff.stop,
            pickup_match=pickup, handover_match=handover, reason=pair.reason,
        )
    for match in (pickup, handover):
        if match is not None:
            notify_match_created(match, http_request=http_request)
    return delivery


def dismiss(tour, pair, user):
    """"Not this": the pair is not suggested on this tour again."""
    return Delivery.objects.create(
        tour=tour, offer=pair.offer, wish=pair.wish, bringer=user, reason=pair.reason,
        pickup_stop=pair.pickup.stop, dropoff_stop=pair.dropoff.stop, dismissed_at=timezone.now(),
    )


def _given_away(listing, now):
    """Mark an offer given away, or a wish covered, once what is agreed takes or brings
    all of it."""
    if listing.covered_at is None and listing.status == Listing.STATUS_PROMISED:
        listing.covered_at = now
        listing.save(update_fields=["covered_at"])


def picked_up(delivery):
    now = timezone.now()
    with transaction.atomic():
        delivery.picked_up_at = now
        delivery.save(update_fields=["picked_up_at"])
        if delivery.pickup_match is not None:
            # The day it happened, as for any gift
            Match.objects.filter(pk=delivery.pickup_match_id).update(proposed_date=now)
        _given_away(delivery.offer, now)


def handed_over(delivery):
    """Handed over: the wish counts as covered once all of it is, and the giver, the
    receiver and the bringer are asked for references from now on."""
    now = timezone.now()
    with transaction.atomic():
        delivery.delivered_at = now
        delivery.save(update_fields=["delivered_at"])
        Match.objects.filter(pk=delivery.handover_match_id).update(proposed_date=now)
        if not delivery.needs_pickup:
            _given_away(delivery.offer, now)
        _given_away(delivery.wish, now)


def withdraw_other(delivery, user, http_request=None):
    """One side said no: the bringer takes back their request to the other side."""
    match = delivery.open_match_left()
    if match is None or match.from_user_id != user.pk:
        return None
    body = _("The other side can't take part, so this delivery doesn't work out. I'm taking my request back.")
    with transaction.atomic():
        MatchMessage.objects.create(match=match, sender=user, body=body, status_to=Match.STATUS_WITHDRAWN)
        match.status = Match.STATUS_WITHDRAWN
        match.responded_at = timezone.now()
        match.save(update_fields=["status", "responded_at"])
    notify_match_response(match, actor=user, http_request=http_request, message=body)
    return match



# ── The packing list ───────────────────────────────────────────────

def _spot_of(stop, listing, legs, index):
    if stop is not None:
        return Spot(index.get(stop.pk, 0), stop, stop.label)
    position = _on_the_way(listing.point, legs) if listing.point is not None else None
    return Spot(-1 if position is None else position, None, listing.public_place[0] or listing.holder_name)


def packing_list(tour, deliveries, stops=None):
    """What to pick up and hand over where, in route order: [(spot, number of the stop
    or None on the way, [("pick" or "hand", delivery)])]. Only what both sides agreed
    to; one's own gifts travel from the start and are only handed over."""
    stops = tour.ordered_stops() if stops is None else stops
    index = {stop.pk: i for i, stop in enumerate(stops)}
    legs = _legs(stops)
    places = {}
    for delivery in deliveries:
        if not delivery.is_agreed:
            continue
        ends = [("hand", _spot_of(delivery.dropoff_stop, delivery.wish, legs, index))]
        if delivery.needs_pickup:
            ends.insert(0, ("pick", _spot_of(delivery.pickup_stop, delivery.offer, legs, index)))
        for what, spot in ends:
            key = ("stop", spot.stop.pk) if spot.stop is not None else ("way", round(spot.position, 2), spot.label)
            place = places.setdefault(key, (spot, []))
            place[1].append((what, delivery))
    rows = sorted(places.values(), key=lambda row: row[0].position)
    return [
        (spot, index[spot.stop.pk] + 1 if spot.stop is not None else None, sorted(items, key=lambda item: item[0] != "pick"))
        for spot, items in rows
    ]
