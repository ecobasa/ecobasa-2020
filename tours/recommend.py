"""Where a tour could go: communities and events near its route, each with the reasons it
is worth a visit (shown as pills, never as a bare score), the place on the route where it
adds the fewest kilometres, and how many. And an order for the stops that adds up to
fewer kilometres.

Candidates are every community with an ambassador and a place in the area, and their
current events. Places are the ones everyone may see (a private community's rough
place), so nothing here gives a door away. Plain Python over a small set found by
PostGIS: no external service, no data to download."""

from collections import namedtuple
from dataclasses import dataclass, field
from datetime import timedelta

from django.contrib.gis.measure import D
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from communities.models import Community
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.matches.matching import distance_km, fit, side_of

from .models import ROAD_FACTOR

# What each reason adds to a candidate's rank
W_LEARN = 4  # per skill the tour wants to learn that is taught there (at most MAX_COUNTED)
W_NEEDS = 3  # per need or wish there the travellers can cover (at most MAX_COUNTED)
W_DAYS = 3  # an event happens in the days the tour could be there
W_FOOD = 1
W_BED = 1
W_ROOM = 2  # room for the group in those days
W_LITTLE_ROOM = -4  # no room for the group then: ranked down, still shown
W_ON_THE_WAY = 3  # the full weight for no extra km, less the more it adds
W_GIFTS = 2  # gifts could travel between it and a stop of the tour
W_ACTIVE = 1  # its ambassador was around lately
W_REFERENCES = 1  # others wrote about it
MAX_COUNTED = 2

# The distances to choose from around the route, and the one the planner starts with
AREA_CHOICES = (25, 50, 100, 250)
DEFAULT_AREA_KM = 50
# The most communities looked at, nearest the route first; their events come with them
MAX_CANDIDATES = 200
# Up to this many extra km a candidate is "on the way"
ON_THE_WAY_KM = 30
ACTIVE_DAYS = 60
# How long a stay is taken to be when only one of its days is known: about a week, as
# hosts gain most from help after that
STAY_DAYS = 7
# The most stops "Suggest an order" reorders
MAX_ORDER_STOPS = 12

Reason = namedtuple("Reason", "key text icon")


@dataclass
class Recommendation:
    community: Community
    event: Event | None
    place: str  # as everyone sees it
    point: object
    position: int  # the index it would get among the stops
    extra_km: int | None
    reasons: list = field(default_factory=list)
    score: float = 0

    @property
    def host(self):
        return self.event or self.community

    @property
    def name(self):
        return self.event.title if self.event else self.community.name

    @property
    def icon(self):
        return self.event.kind_icon if self.event else self.community.get_type_icon()

    @property
    def rough(self):
        return not self.community.place_is_public

    def add(self, key, text, icon, weight):
        self.reasons.append(Reason(key, text, icon))
        self.score += weight


def _public_points(stops):
    return [stop.public_place()[1] for stop in stops]


def best_position(points, point):
    """(index, extra km) where `point` adds the least to the path through `points` (None
    for a stop without a place, which is skipped). Before the first, between two, or
    after the last; at the end of a route with no places."""
    known = [(i, p) for i, p in enumerate(points) if p is not None]
    if not known:
        return len(points), None
    options = [(known[0][0], distance_km(point, known[0][1])), (len(points), distance_km(known[-1][1], point))]
    for (i, a), (j, b) in zip(known, known[1:]):
        options.append((j, distance_km(a, point) + distance_km(point, b) - distance_km(a, b)))
    index, km = min(options, key=lambda option: option[1])
    return index, round(km * ROAD_FACTOR)


def window(stops, position, tour):
    """(first, last) day the tour could be at a stop inserted at `position`: from when it
    leaves the stop before to when it arrives at the one after. A missing end is
    STAY_DAYS from the other; without either, the tour's own days. (None, None) if
    nothing is known."""
    before = stops[position - 1] if position > 0 else None
    after = stops[position] if position < len(stops) else None
    start = (before.leave_on or before.arrive_on) if before else None
    end = (after.arrive_on or after.leave_on) if after else None
    if start is None and end is None:
        return tour.starts_on, tour.ends_on
    if start is None:
        start = end - timedelta(days=STAY_DAYS)
    if end is None:
        end = start + timedelta(days=STAY_DAYS)
    return (start, end) if start <= end else (end, start)


def _area(tour, stops, area_km):
    """The communities in the area that the tour doesn't stay at yet: around the route,
    or its one stop, else in the tour's countries. Nearest first (not in the countries
    case), at most MAX_CANDIDATES."""
    stays = {stop.community_id for stop in stops if stop.community_id and not stop.event_id}
    communities = (
        Community.objects.exclude(owner=None).exclude(location=None).exclude(pk__in=stays).select_related("owner")
    )
    points = [p for p in _public_points(stops) if p is not None]
    where = tour.route if tour.route is not None else (points[0] if points else None)
    if where is not None:
        from django.contrib.gis.db.models.functions import Distance

        return list(
            communities.filter(location__dwithin=(where, D(km=area_km)))
            .annotate(away=Distance("location", where)).order_by("away")[:MAX_CANDIDATES]
        )
    codes = [country.code for country in tour.countries]
    if not codes:
        return []
    return list(communities.filter(country__in=codes).order_by("pk")[:MAX_CANDIDATES])


def _first(listings):
    return listings[0].display_title + (f" +{len(listings) - 1}" if len(listings) > 1 else "")


def recommend_stops(tour, area_km=DEFAULT_AREA_KM, limit=10):
    """Communities and events worth a stop, best first: [Recommendation]. Not the ones
    the tour stops at already."""
    stops = tour.ordered_stops()
    points = _public_points(stops)
    communities = _area(tour, stops, area_km)
    if not communities:
        return []
    at_stops = {stop.event_id for stop in stops if stop.event_id}
    # Where it stops at an event, only the community's other events are new
    visited = {stop.community_id for stop in stops if stop.community_id}
    events = list(
        Event.objects.current().filter(community__in=communities).exclude(pk__in=at_stops).select_related("community")
    )

    candidates = []
    for community in communities:
        name, point = community.rough_place()
        if point is None:
            continue
        position, extra = best_position(points, point)
        if community.pk not in visited:
            candidates.append(Recommendation(community, None, name, point, position, extra))
        for event in (e for e in events if e.community_id == community.pk):
            candidates.append(Recommendation(community, event, name, point, position, extra))
    if not candidates:
        return []

    _rank_by_what_happens_there(tour, candidates)
    for candidate in candidates:
        _rank_by_days(tour, stops, candidate)
        _rank_by_way(candidate, area_km)
    # The reasons that cost a query each, only for the best of them
    candidates.sort(key=lambda c: -c.score)
    shortlist = candidates[:limit * 2]
    group = max(sum(t.people for t in tour.counted_travellers()), 1)
    _rank_by_gifts(stops, shortlist)
    for candidate in shortlist:
        _rank_by_room(tour, stops, candidate, group)
        _rank_by_trust(candidate)
    shortlist = [c for c in shortlist if c.reasons]
    shortlist.sort(key=lambda c: (-c.score, c.extra_km if c.extra_km is not None else 0, c.name.lower()))
    return shortlist[:limit]


def _rank_by_what_happens_there(tour, candidates):
    """What one can learn there that the tour wants to learn, and what it needs that the
    travellers can do or bring: an event's own offers and needs, a community's own
    (its events are candidates of their own)."""
    learn = set(tour.learn_skills.values_list("pk", flat=True))
    people = [traveller.user_id for traveller in tour.counted_travellers()]
    offers = [
        side for side in (
            side_of(offer) for offer in Listing.objects.current()
            .filter(owner__in=people, community=None, type=Listing.TYPE_OFFER).select_related("owner", "skill")
        ) if side is not None
    ]
    communities = {c.community.pk for c in candidates}
    listings = list(
        Listing.objects.current().filter(Q(community__in=communities) | Q(event__community__in=communities))
        .select_related("skill", "owner", "community__owner", "event__community")
    )
    for candidate in candidates:
        if candidate.event:
            here = [l for l in listings if l.event_id == candidate.event.pk]
        else:
            here = [l for l in listings if l.community_id == candidate.community.pk and l.event_id is None]
        taught = {}
        for listing in here:
            if listing.is_offer and listing.skill_id in learn:
                taught.setdefault(listing.skill_id, listing)
        if taught:
            found = sorted(taught.values(), key=lambda l: l.display_title)
            candidate.add("learn", _("Learn: %(what)s") % {"what": _first(found)}, "fa-graduation-cap",
                          W_LEARN * min(len(found), MAX_COUNTED))
        wishes = [l for l in here if l.is_wish and l.status == l.STATUS_OPEN]
        covered = []
        for wish in wishes:
            side = side_of(wish)
            if side is not None and any(fit(side, offer) for offer in offers):
                covered.append(wish)
        if covered:
            covered.sort(key=lambda l: l.display_title)
            candidate.add("needs", _("Needs: %(what)s") % {"what": _first(covered)}, "fa-hand-holding-heart",
                          W_NEEDS * min(len(covered), MAX_COUNTED))
        if candidate.event:
            if candidate.event.food_provided:
                candidate.add("food", _("Food provided"), "fa-utensils", W_FOOD)
            if candidate.event.bed_provided:
                candidate.add("bed", _("Bed provided"), "fa-bed", W_BED)


def _rank_by_days(tour, stops, candidate):
    """An event that happens in the days the tour could be there. An ongoing one is
    always on, so it is no reason."""
    event = candidate.event
    if event is None or event.ends_on is None:
        return
    start, end = window(stops, candidate.position, tour)
    if start is None and end is None:
        return
    begins = event.starts_on or event.ends_on
    if (end is None or begins <= end) and (start is None or event.ends_on >= start):
        candidate.add("days", _("Fits your days"), "fa-calendar-check", W_DAYS)


def _rank_by_way(candidate, area_km):
    if candidate.extra_km is None:
        return
    if candidate.extra_km <= ON_THE_WAY_KM:
        candidate.add("way", _("On the way"), "fa-route", W_ON_THE_WAY)
    else:
        # Less the further it leads away, nothing at the edge of the area
        candidate.score += W_ON_THE_WAY * max(0, 1 - candidate.extra_km / (2 * area_km * ROAD_FACTOR))


def _rank_by_room(tour, stops, candidate, group):
    """Whether the community has room for the group in the days the tour could be there:
    its room for guests against the confirmed people on its busiest day then."""
    from gift_economy.matches.calendar import stays_of

    community = candidate.community
    start, end = window(stops, candidate.position, tour)
    if community.max_guests is None or start is None or end is None:
        return
    dated, _undated = stays_of(community)
    busiest = 0
    day = start
    while day <= end and day <= start + timedelta(days=60):
        busiest = max(busiest, sum(s.people for s in dated if s.confirmed and s.covers(day)))
        day += timedelta(days=1)
    free = community.max_guests - busiest
    if free >= group:
        candidate.add("room", _("Room for %(n)s") % {"n": free}, "fa-bed", W_ROOM)
    else:
        candidate.add("little_room", _("Little room then"), "fa-triangle-exclamation", W_LITTLE_ROOM)


def _rank_by_gifts(stops, candidates):
    """Gifts could travel: a thing offered there is wished for at a stop of the tour, or
    the other way round. Skills don't travel, things do."""
    hosts = Q(community__in={s.community_id for s in stops if s.community_id and not s.event_id}) | Q(
        event__in={s.event_id for s in stops if s.event_id}
    )
    on_route = [
        side for side in (side_of(l) for l in _things().filter(hosts)) if side is not None
    ]
    if not on_route:
        return
    communities = {c.community.pk for c in candidates}
    there = list(_things().filter(Q(community__in=communities) | Q(event__community__in=communities)))
    for candidate in candidates:
        if candidate.event:
            here = [l for l in there if l.event_id == candidate.event.pk]
        else:
            here = [l for l in there if l.community_id == candidate.community.pk and l.event_id is None]
        sides = [side for side in (side_of(l) for l in here) if side is not None]
        if any(fit(a, b) for a in sides for b in on_route):
            candidate.add("gifts", _("Gifts could travel"), "fa-gift", W_GIFTS)


def _things():
    return (
        Listing.objects.current().filter(skill=None, kind__in=Listing.THING_KINDS)
        .select_related("owner", "community__owner", "event__community", "tour__organiser")
    )


def _rank_by_trust(candidate):
    from gift_economy.references.models import references_about

    ambassador = candidate.community.owner
    active = ambassador.last_active if ambassador else None
    if active and active >= timezone.now() - timedelta(days=ACTIVE_DAYS):
        candidate.add("active", _("Active lately"), "fa-circle-check", W_ACTIVE)
    count = references_about(candidate.community).count()
    if count:
        candidate.add("references", ngettext("%(n)s reference", "%(n)s references", count) % {"n": count},
                      "fa-comment", W_REFERENCES)


# ── An order with fewer kilometres ──────────────────────────────────

def _length(points):
    return sum(distance_km(a, b) for a, b in zip(points, points[1:]))


def suggest_order(stops):
    """An order of `stops` that adds up to fewer km, or None if there is nothing to
    reorder (or too many stops). Stops with days keep their order among each other, so
    the dates stay in sequence; so do stops without a place. The others are put where
    they add the least (cheapest insertion), then the way is shortened by turning
    stretches around (2-opt) and moving single stops, as long as no fixed stops swap."""
    if len(stops) > MAX_ORDER_STOPS:
        return None
    points = {stop.pk: stop.public_place()[1] for stop in stops}
    fixed = [s for s in stops if s.arrive_on or s.leave_on or points[s.pk] is None]
    free = [s for s in stops if s not in fixed]
    if not free or len(stops) < 3:
        return None

    def length(order):
        return _length([points[s.pk] for s in order if points[s.pk] is not None])

    order = list(fixed)
    if not [s for s in order if points[s.pk] is not None]:
        # Nothing to build on: start with the two that are furthest apart
        a, b = max(
            ((x, y) for i, x in enumerate(free) for y in free[i + 1:]),
            key=lambda pair: distance_km(points[pair[0].pk], points[pair[1].pk]),
        )
        order += [a, b]
    rest = [s for s in free if s not in order]
    while rest:
        stop, at = min(
            ((s, i) for s in rest for i in range(len(order) + 1)),
            key=lambda option: length(order[:option[1]] + [option[0]] + order[option[1]:]),
        )
        order.insert(at, stop)
        rest.remove(stop)

    def allowed(candidate):
        return [s for s in candidate if s in fixed] == fixed

    improved = True
    while improved:
        improved = False
        best = length(order)
        for i in range(len(order) - 1):
            for j in range(i + 1, len(order)):
                turned = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if allowed(turned) and length(turned) < best - 0.01:
                    order, best, improved = turned, length(turned), True
        for stop in free:
            without = [s for s in order if s is not stop]
            for i in range(len(without) + 1):
                moved = without[:i] + [stop] + without[i:]
                if allowed(moved) and length(moved) < best - 0.01:
                    order, best, improved = moved, length(moved), True
    return order


def km_of(stops):
    """About how many km the way through `stops` is, in this order."""
    points = [p for p in _public_points(stops) if p is not None]
    return round(_length(points) * ROAD_FACTOR)


def hints(tour, stops):
    """The planner's gentle hints from the experience of earlier tours, as they apply:
    never rules."""
    found = []
    if len({s.community_id for s in stops if s.community_id}) < 2:
        found.append(_("Visit at least two communities so gifts can travel."))
    if tour.open_to_join and (tour.max_people is None or tour.max_people > 5):
        found.append(_("3 to 5 people fit into a community most easily; with experience, up to 10."))
    return found
