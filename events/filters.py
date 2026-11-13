from collections import defaultdict
from datetime import date, timedelta

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point, Polygon
from django.db.models import Q
from django.utils import timezone

from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import skill_name_q
from gift_economy.matches.matching import distance_km
from gift_economy.matches.models import Match

from . import kinds

# What an event can need (forms.NeedForm), for "needs help with"
NEED_KINDS = (
    Listing.KIND_HANDS, Listing.KIND_KNOWLEDGE, Listing.KIND_MATERIAL, Listing.KIND_TOOL,
    Listing.KIND_VEHICLE, Listing.KIND_OTHER,
)
# How far ahead an ongoing event is looked at for room
ROOM_DAYS = 90


class EventFilters:
    """The filters of the events map and list, from the query string: when (upcoming,
    past; without it what is not over yet), a search, a country, its kinds, a span of days
    it overlaps (from, until), skills one can learn there (learn: names, any of them), what
    it still needs (needs: kinds, any of them), whether it still has room, one can just
    come, food or a bed is provided, and, logged in, whether it fits one's skills and
    whether one goes there. `near` (lat,lng) is where distances are measured from, `bbox`
    the map's visible area."""

    WHENS = ("upcoming", "past")
    FLAGS = ("open", "food", "bed", "room")

    def __init__(self, params, user=None):
        self.user = user
        signed_in = bool(user and user.is_authenticated)
        when = params.get("when", "")
        self.when = when if when in self.WHENS else ""
        self.q = (params.get("q") or "").strip()
        country = (params.get("country") or "").strip().upper()
        self.country = country if len(country) == 2 and country.isalpha() else ""
        self.kinds = [kind for kind in _list(params.get("kind")) if kind in kinds.TEXTS]
        self.since = _day(params.get("from"))
        self.until = _day(params.get("until"))
        self.learn = [name.strip('"') for name in _list(params.get("learn")) if name.strip('"')]
        self.needs = [kind for kind in _list(params.get("needs")) if kind in NEED_KINDS]
        self.open, self.food, self.bed, self.room = (params.get(flag) == "1" for flag in self.FLAGS)
        self.fits = signed_in and params.get("fits") == "1"
        self.going = signed_in and params.get("going") == "1"
        self.near = _point(params.get("near"))
        self.bbox = _bbox(params.get("bbox"))

    @property
    def count(self):
        """How many of the filters behind the filter button are in use."""
        return sum(map(bool, (
            self.when, self.kinds, self.since or self.until, self.learn, self.needs,
            self.room, self.open, self.food, self.bed, self.fits, self.going,
        )))

    @property
    def active(self):
        return bool(self.count or self.q or self.country or self.near)

    def base(self, events):
        """Of `events`, those of the time asked for."""
        today = timezone.localdate()
        if self.when == "past":
            return events.filter(ends_on__lt=today)
        events = events.current()
        if self.when == "upcoming":
            events = events.filter(starts_on__gt=today)
        return events

    def apply(self, events):
        if self.q:
            events = events.filter(
                Q(title__icontains=self.q)
                | Q(description__icontains=self.q)
                | Q(community__name__icontains=self.q)
                | Q(community__location_name__icontains=self.q)
                | Q(listings__title__icontains=self.q)
                | skill_name_q(self.q, "listings__skill__")
            )
        if self.country:
            events = events.filter(community__country=self.country)
        if self.kinds:
            events = events.filter(kind__in=self.kinds)
        if self.since:
            events = events.filter(Q(ends_on=None) | Q(ends_on__gte=self.since))
        if self.until:
            events = events.filter(Q(starts_on=None) | Q(starts_on__lte=self.until))
        if self.learn:
            wanted = Q()
            for name in self.learn:
                wanted |= skill_name_q(name, "listings__skill__")
            events = events.filter(Q(listings__type=Listing.TYPE_OFFER) & wanted)
        if self.needs:
            open_needs = Listing.objects.open().filter(type=Listing.TYPE_WISH, event__isnull=False, kind__in=self.needs)
            events = events.filter(pk__in=[need.event_id for need in open_needs if need.status == need.STATUS_OPEN])
        if self.open:
            events = events.filter(is_open=True)
        if self.food:
            events = events.filter(food_provided=True)
        if self.bed:
            events = events.filter(bed_provided=True)
        if self.fits:
            events = events.filter(pk__in=fits_skills(self.user))
        if self.going:
            events = events.filter(pk__in=going_to(self.user))
        events = events.distinct()
        if self.room:
            events = events.filter(pk__in=with_room(events))
        return events

    def in_view(self, events):
        """Of `events`, those in the map's visible area, each with `point`: where everyone
        sees it."""
        found = []
        for event in events:
            event.point = event.place.rough_place()[1]
            if event.point is not None and (self.bbox is None or self.bbox.contains(event.point)):
                found.append(event)
        return found

    def order(self, events, home=None):
        """Nearest `near` (else `home`) first, each with `km`; those without a place last.
        Among equals: the soonest upcoming, the latest past, otherwise the freshest."""
        origin = self.near or home
        for event in events:
            point = event.place.rough_place()[1]
            event.km = round(distance_km(origin, point)) if origin is not None and point is not None else None
        if self.when == "upcoming":
            tie = lambda event: event.starts_on.toordinal()
        elif self.when == "past":
            tie = lambda event: -event.ends_on.toordinal()
        else:
            tie = lambda event: -event.updated_at.timestamp()
        return sorted(events, key=lambda event: (event.km is None, event.km or 0, tie(event)))


def fits_skills(user):
    """The pks of events with an open need `user` can cover with a skill they offer, or
    where one can learn what they wish to learn (a queryset of pks)."""
    own = Listing.objects.open().filter(owner=user, community=None, skill__isnull=False)
    offers = own.filter(type=Listing.TYPE_OFFER).exclude(available=False).values("skill_id")
    wishes = own.filter(type=Listing.TYPE_WISH, kind=Listing.KIND_SKILL).values("skill_id")
    listings = Listing.objects.open().filter(event__isnull=False).filter(
        Q(type=Listing.TYPE_WISH, skill_id__in=offers) | Q(type=Listing.TYPE_OFFER, skill_id__in=wishes)
    )
    return listings.values("event_id")


def _accepted(user=None, events=None):
    """Accepted matches to events: one's coming or one's help, of `user` or to `events`."""
    from .models import Event

    matches = Match.objects.filter(content_type=ContentType.objects.get_for_model(Event), status=Match.STATUS_ACCEPTED)
    if user is not None:
        matches = matches.filter(from_user=user)
    if events is not None:
        # A match's object_id is text: the ids, not a join
        matches = matches.filter(object_id__in=[str(pk) for pk in events.values_list("pk", flat=True)])
    return matches


def going_to(user):
    """The pks of the events `user` comes to or helps with, accepted."""
    return [int(pk) for pk in _accepted(user).values_list("object_id", flat=True)]


def with_room(events):
    """The pks of `events` that take people and still have room on some day ahead: as
    many as they want at a time minus those coming then. Without a number, any room."""
    today = timezone.localdate()
    stays = defaultdict(list)
    for match in _accepted(events=events).select_related("stay_details"):
        details = getattr(match, "stay_details", None)
        if details is not None:
            stays[int(match.object_id)].append(details)
    pks = []
    for event in events:
        if not event.takes_people():
            continue
        if not event.volunteers_wanted:
            pks.append(event.pk)
            continue
        first = max(today, event.starts_on or today)
        last = event.ends_on or first + timedelta(days=ROOM_DAYS)
        days = (first + timedelta(days=n) for n in range((last - first).days + 1))
        if any(_people_on(day, stays[event.pk]) < event.volunteers_wanted for day in days):
            pks.append(event.pk)
    return pks


def _people_on(day, stays):
    """How many come on `day`: a stay without days counts on all of them."""
    return sum(
        stay.people or 1 for stay in stays
        if (stay.stay_from is None or timezone.localdate(stay.stay_from) <= day)
        and (stay.stay_to is None or day <= timezone.localdate(stay.stay_to))
    )


def _list(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _day(value):
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return None


def _point(value):
    """"lat,lng" → a point, or None."""
    try:
        lat, lng = (float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return Point(lng, lat, srid=4326)


def _bbox(value):
    """"west,south,east,north" → a polygon, or None."""
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    bbox = Polygon.from_bbox((west, south, east, north))
    bbox.srid = 4326
    return bbox
