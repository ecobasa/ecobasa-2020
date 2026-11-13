"""Tours on a map: the filters of the tours index, and a tour as GeoJSON.

Every point here is a public one (Stop.public_place): a private community, and an event
there, only as its rough place. So no payload gives a door away (plan 5.5, rule 1).
"""
from datetime import date

from django.contrib.gis.geos import Point, Polygon
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.text import Truncator

from gift_economy.matches.matching import distance_km
from users.places import approximate, town

# The most tours one request sends to a map
MAX_TOURS = 200

# A stop's pin: a Font Awesome codepoint and a colour of the theme (tailwind.config.js).
# Communities as on the communities map (by type), events in brown with their kind's
# icon, another place as a plain pin.
COMMUNITY_PINS = {
    "f": (0xF4D8, "#5A5527"),  # Permaculture Farm: seedling
    "e": (0xE537, "#b4502c"),  # Ecovillage: people-roof
    "c": (0xE3AF, "#de7a08"),  # Commune: house-chimney
    "h": (0xE3AF, "#e34a26"),  # Houseproject: house-chimney
    "p": (0xF6E3, "#ff7800"),  # Place for Projects: hammer
}
COMMUNITY_PIN = (0xF015, "#da6137")  # house
EVENT_PINS = {
    "project": (0xF85E, "#452912"),  # brown, person-digging
    "community_event": (0xE533, "#452912"),  # brown, people-group
}
# The travel modes' icons (Tour.MODE_ICONS) as codepoints, for the map's canvas
MODE_CODEPOINTS = {
    "van": 0xF5B6,  # van-shuttle
    "car": 0xF5E4,  # car-side
    "bicycle": 0xF206,
    "train": 0xF238,
    "hitchhiking": 0xF164,  # thumbs-up
    "foot": 0xF6EC,  # person-hiking
    "boat": 0xE445,  # sailboat
    "mixed": 0xF4D7,  # route
}
PLACE_PIN = (0xF3C5, "#da6137")  # primary, location-dot
# A tour idea without stops, at about where its organiser lives
IDEA_PIN = (0xF207, "#80143b")  # purple, bus


def stop_pin(stop):
    if stop.event_id:
        return EVENT_PINS.get(stop.event.kind, EVENT_PINS["community_event"])
    if stop.community_id:
        return COMMUNITY_PINS.get(stop.community.type, COMMUNITY_PIN)
    return PLACE_PIN


def idea_home(tour, user):
    """Where a tour idea without stops shows on the map: about where its organiser lives
    (users.places, never their door), and only to people logged in, who also see who
    organises it. (name, point) or (None, None)."""
    organiser = tour.organiser
    if not (user and user.is_authenticated and tour.is_idea and organiser and organiser.location):
        return None, None
    if any(stop.public_place()[1] is not None for stop in tour.stops.all()):
        return None, None
    return town(organiser.location_name) or "", approximate(organiser.location, organiser.pk)


def tour_points(tour, user=None):
    """The points a tour shows on the map: its stops as everyone sees them, or an idea's
    rough home."""
    points = [point for _name, point in (stop.public_place() for stop in tour.stops.all()) if point is not None]
    if not points:
        point = idea_home(tour, user)[1]
        if point is not None:
            points.append(point)
    return points


def _day(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _point(value):
    """"lat,lon" → a point, or None."""
    try:
        lat, lon = (float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return Point(lon, lat, srid=4326)


def _bbox(value):
    """"west,south,east,north" → a polygon, or None."""
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except (AttributeError, ValueError):
        return None
    polygon = Polygon.from_bbox((max(west, -180), max(south, -90), min(east, 180), min(north, 90)))
    polygon.srid = 4326
    return polygon


def search_q(q):
    """Tours whose title, description or "good to know" match, that want to learn a
    skill of that name (in any language), or that stop at a place, community or event
    of that name, or at a host one of whose current gifts (offers and wishes) or events
    matches ("clay" finds the tour that stops where clay is offered or needed). Not by
    a community's address: a private one's would give its street away."""
    from events.models import Event
    from gift_economy.gifts.models import Listing
    from gift_economy.gifts.skills.models import skill_name_q

    events = Event.objects.current().filter(Q(title__icontains=q) | Q(description__icontains=q))
    listings = Listing.objects.current().filter(Q(title__icontains=q) | Q(description__icontains=q) | skill_name_q(q))
    return (
        Q(title__icontains=q)
        | Q(description__icontains=q)
        | Q(good_to_know__icontains=q)
        | skill_name_q(q, "learn_skills__")
        | Q(stops__name__icontains=q)
        | Q(stops__community__name__icontains=q)
        | Q(stops__event__in=events)
        | Q(stops__community__in=listings.filter(community__isnull=False).values("community_id"))
        | Q(stops__event__in=listings.filter(event__isnull=False).values("event_id"))
    )


class TourFilters:
    """The filters of the tours index, read from the query string: tours with dates or
    tour ideas only (show), a search, when (from, until), what it wants to learn (skill names, any of them), how it travels, children
    or animals welcome, and the map's visible area. `near` (lat,lon) only sorts the
    list, nearest first."""

    def __init__(self, params, user=None):
        self.user = user
        self.show = params.get("show") if params.get("show") in ("tours", "ideas") else ""
        self.q = (params.get("q") or "").strip()
        self.since = _day(params.get("from"))
        self.until = _day(params.get("until"))
        names = (params.get("learn") or "").split(",")
        self.learn = [name.strip().strip('"') for name in names if name.strip().strip('"')]
        self.mode = params.get("mode") or ""
        self.children = params.get("children") == "1"
        self.animals = params.get("animals") == "1"
        country = (params.get("country") or "").strip().upper()
        self.country = country if len(country) == 2 and country.isalpha() else ""
        self.near = _point(params.get("near"))
        self.bbox = _bbox(params.get("bbox"))

    @property
    def active(self):
        return bool(self.show or self.country or self.q or self.since or self.until or self.learn or self.mode or self.children or self.animals)

    def apply(self, tours):
        """Narrow a queryset of tours. Tour ideas have no dates: the dates leave them be."""
        from gift_economy.gifts.skills.models import skill_name_q

        if self.show == "tours":
            tours = tours.exclude(starts_on=None, ends_on=None)
        elif self.show == "ideas":
            tours = tours.filter(starts_on=None, ends_on=None)
        if self.country:
            # Stored as "DE,NL,FR"
            tours = tours.filter(countries__regex=rf"(^|,){self.country}(,|$)")
        if self.q:
            tours = tours.filter(search_q(self.q))
        if self.since:
            tours = tours.filter(Q(ends_on=None) | Q(ends_on__gte=self.since))
        if self.until:
            tours = tours.filter(Q(starts_on=None) | Q(starts_on__lte=self.until))
        if self.learn:
            wanted = Q()
            for name in self.learn:
                wanted |= skill_name_q(name, "learn_skills__")
            tours = tours.filter(wanted)
        if self.mode:
            tours = tours.filter(travel_mode=self.mode)
        if self.children:
            tours = tours.filter(children_welcome=True)
        if self.animals:
            tours = tours.filter(animals_welcome=True)
        return tours.distinct()

    def by_distance(self, tours):
        """`tours` nearest `near` first (by their nearest stop as everyone sees it), each
        with `km`; unchanged without `near`."""
        tours = list(tours)
        if self.near is None:
            return tours
        for tour in tours:
            points = tour_points(tour, self.user)
            tour.km = round(min(distance_km(self.near, point) for point in points)) if points else None
        return sorted(tours, key=lambda tour: (tour.km is None, tour.km or 0))

    def in_view(self, tours):
        """Of `tours`, those with a line or a stop in the map's visible area."""
        if self.bbox is None:
            return list(tours)
        found = []
        for tour in tours:
            if tour.route is not None:
                if tour.route.intersects(self.bbox):
                    found.append(tour)
            elif any(self.bbox.contains(point) for point in tour_points(tour, self.user)):
                found.append(tour)
        return found


def stop_image(stop):
    """A picture of the stop: its event's, else the first photo of its community."""
    if stop.event_id and stop.event.image:
        return stop.event.image.url
    if stop.community_id:
        photo = next(iter(stop.community.photos.all()), None)
        if photo and photo.image:
            return photo.image.url
    return ""


def tour_state(tour):
    if tour.is_over:
        return "past"
    if tour.is_idea:
        return "idea"
    return "upcoming"


def tour_features(tour, user=None):
    """The tour as GeoJSON features: its route line (with each leg's travel mode) and its
    numbered stops, at the places everyone may see, each stop with its pin (icon, color);
    an idea without stops as a bus at about where its organiser lives (idea_home). Every
    feature carries what a popup tells of the tour; the organiser's name only for people
    logged in, as on the tour's page."""
    organiser = tour.organiser
    props = {
        "slug": tour.slug,
        "title": tour.title,
        "url": tour.get_absolute_url(),
        "dates": render_to_string("tours/_tour_dates.html", {"tour": tour}).strip(),
        "state": tour_state(tour),
        "km": tour.distance_km,
        "image": tour.image.url if tour.image else "",
        "mode_icon": tour.travel_mode_icon,
        "mode": str(tour.get_travel_mode_display()),
        "description": Truncator(tour.description).chars(160),
        "learn": [skill.get_name() for skill in list(tour.learn_skills.all())[:4]],
        "organiser": organiser.name if organiser and user and user.is_authenticated else "",
    }
    # How it goes on from each stop that is on the map to the next one
    on_map = [stop for stop in tour.stops.all() if stop.public_place()[1] is not None]
    leg_modes = [MODE_CODEPOINTS.get(stop.onward_mode or tour.travel_mode, 0xF4D7) for stop in on_map[:-1]]
    features = []
    if tour.route is not None:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [list(c) for c in tour.route.coords]},
            "properties": {**props, "kind": "route", "leg_modes": leg_modes},
        })
    stops = list(tour.stops.all())
    for number, stop in enumerate(stops, start=1):
        name, point = stop.public_place()
        if point is None:
            continue
        label = stop.label
        if stop.event_id:
            label = f"{stop.event.title} · {stop.community.name}"
        icon, color = stop_pin(stop)
        if stop.event_id:
            link = stop.event.get_absolute_url()
        elif stop.community_id:
            link = stop.community.get_absolute_url()
        else:
            link = ""
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
            "properties": {
                **props, "kind": "stop", "number": number, "stop_count": len(stops), "name": label, "place": name or "",
                "icon": icon, "color": color, "link": link, "stop_image": stop_image(stop),
                "stop_dates": render_to_string("tours/_stop_dates.html", {"stop": stop}).strip(),
                # Shown as an area, not a pin, so it doesn't look like an address
                "rough": bool(stop.community_id and not stop.community.place_is_public),
            },
        })
    if not features:
        name, point = idea_home(tour, user)
        if point is not None:
            icon, color = IDEA_PIN
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
                "properties": {**props, "kind": "home", "place": name, "icon": icon, "color": color, "rough": True},
            })
    return features


def feature_collection(tours, user=None):
    return {"type": "FeatureCollection", "features": [f for tour in tours for f in tour_features(tour, user)]}
