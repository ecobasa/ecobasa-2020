from collections import namedtuple

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.contrib.gis.geos import LineString
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _, ngettext, pgettext_lazy
from django_countries.fields import CountryField

from communities.models import Community
from events.models import Event
from gift_economy.matches.matching import distance_km

# Straight distance times this is about the way on roads (no routing service needed)
ROAD_FACTOR = 1.3

# The way from one stop to the next: not stored, leg i runs from stop i to stop i+1
Leg = namedtuple("Leg", "index start end km")


class TourQuerySet(models.QuerySet):
    def published(self):
        return self.filter(published_at__isnull=False)

    def listed(self):
        """What the list of tours shows: published and shown in the list and on the map
        (a personal tour only if its traveller chose so)."""
        return self.published().filter(listed=True)

    def current(self):
        """Not archived and not over yet. Tour ideas, without dates, stay current as long
        as someone keeps them up to date."""
        today = timezone.localdate()
        return self.filter(archived_at=None).filter(models.Q(ends_on=None) | models.Q(ends_on__gte=today))


class Tour(models.Model):
    """A journey from stop to stop: someone travels from event to event and from community
    to community, to help, to learn and to take gifts along. Others can travel along for
    the whole route or part of it, unless it is one person's own tour (`open_to_join`).

    Without dates it is a tour idea: someone looking for companions, a vehicle or a route.
    Its dates, countries, route line and distance follow from its stops (rebuild_route).
    The route goes through the places everyone may see, never a private community's door.
    """

    MODE_VAN = "van"
    MODE_CAR = "car"
    MODE_BICYCLE = "bicycle"
    MODE_TRAIN = "train"
    MODE_HITCHHIKING = "hitchhiking"
    MODE_FOOT = "foot"
    MODE_BOAT = "boat"
    MODE_MIXED = "mixed"
    MODE_CHOICES = [
        (MODE_VAN, _("Van or bus")),
        (MODE_CAR, _("Car")),
        (MODE_BICYCLE, _("Bicycle")),
        (MODE_TRAIN, _("Train and bus")),
        (MODE_HITCHHIKING, _("Hitchhiking")),
        (MODE_FOOT, _("On foot")),
        (MODE_BOAT, _("Boat")),
        (MODE_MIXED, _("Mixed")),
    ]
    MODE_ICONS = {
        MODE_VAN: "fa-van-shuttle",
        MODE_CAR: "fa-car-side",
        MODE_BICYCLE: "fa-bicycle",
        MODE_TRAIN: "fa-train",
        MODE_HITCHHIKING: "fa-thumbs-up",
        MODE_FOOT: "fa-person-hiking",
        MODE_BOAT: "fa-sailboat",
        MODE_MIXED: "fa-route",
    }

    # Not usable as a slug: they are paths beside a tour's page
    RESERVED_SLUGS = ("new", "api", "mine", "offer-a-ride")

    slug = models.SlugField(_("Slug"), max_length=255, unique=True, blank=True)
    title = models.CharField(_("Title"), max_length=255)
    description = models.TextField(_("Description"), blank=True)
    image = models.ImageField(_("image"), upload_to="tours-images", null=True, blank=True)
    organiser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="organised_tours", verbose_name=_("Organiser"),
    )
    learn_skills = models.ManyToManyField(
        "gifts.Skill", blank=True, related_name="tours", verbose_name=_("What we want to learn"),
    )
    travel_mode = models.CharField(_("How we travel"), max_length=20, choices=MODE_CHOICES, default=MODE_VAN)
    open_to_join = models.BooleanField(_("I'm looking for travellers"), default=True)
    max_people = models.PositiveSmallIntegerField(
        _("How many people at most?"), null=True, blank=True, help_text=_("Including you."),
    )
    # A personal tour is shown only if its traveller chooses so; one that looks for
    # travellers always is (save)
    listed = models.BooleanField(_("Show this tour in the list and on the map"), default=False)
    children_welcome = models.BooleanField(_("Children welcome"), default=False)
    animals_welcome = models.BooleanField(_("Animals welcome"), default=False)
    good_to_know = models.TextField(_("Good to know"), blank=True)
    costs_note = models.CharField(
        _("How we share costs"), max_length=255, blank=True,
        help_text=_("e.g. we share fuel, everyone brings food for the road"),
    )
    published_at = models.DateTimeField(_("Published"), null=True, blank=True)

    # Filled from the stops (rebuild_route)
    starts_on = models.DateField(_("From"), null=True, blank=True)
    ends_on = models.DateField(_("Until"), null=True, blank=True)
    # Chosen by hand while it has no stops
    countries = CountryField(_("Countries"), multiple=True, multiple_sort=False, blank=True)
    route = models.LineStringField(_("Route"), geography=True, null=True, blank=True)
    # Where it starts, as everyone may see it (also with a single stop): where its needs
    # are on the gifts map
    start = models.PointField(_("Start"), geography=True, null=True, blank=True)
    distance_km = models.PositiveIntegerField(_("About how many km"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    # Bumped whenever the tour or its stops change, or an organiser confirms it is still
    # current. Not auto_now: archiving must not make a tour look fresh.
    updated_at = models.DateTimeField(_("Updated"), default=timezone.now)
    stale_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(_("Archived"), null=True, blank=True)

    # The join requests (a Match each, with its Traveller)
    matches = GenericRelation("matches.Match")

    objects = TourQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Tour")
        verbose_name_plural = _("Tours")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._free_slug()
        if self.open_to_join:
            self.listed = True
        super().save(*args, **kwargs)
        # The organiser travels too: on the whole route, or on the stretch they joined for
        update_fields = kwargs.get("update_fields")
        if self.organiser_id and (update_fields is None or "organiser" in update_fields):
            own = next((t for t in self.travellers.filter(user_id=self.organiser_id).select_related("match") if t.is_counted), None)
            if own is None:
                Traveller.objects.create(tour=self, user_id=self.organiser_id, is_organiser=True)
            elif not own.is_organiser:
                own.is_organiser = True
                own.save(update_fields=["is_organiser"])

    def _free_slug(self):
        base = slugify(self.title)[:240] or "tour"
        taken = set(Tour.objects.filter(slug__startswith=base).values_list("slug", flat=True))
        taken.update(self.RESERVED_SLUGS)
        slug, suffix = base, 1
        while slug in taken:
            suffix += 1
            slug = f"{base}-{suffix}"
        return slug

    def url(self, name="detail", *args):
        return reverse(f"tours:{name}", args=[self.slug, *args])

    def get_absolute_url(self):
        return self.url()

    @property
    def header_image(self):
        """Its picture, else its first vehicle's (a URL, or ""): the tour page's header
        and the map's popovers."""
        if self.image:
            return self.image.url
        vehicle = next((vehicle for vehicle in self.vehicles.all() if vehicle.image), None)
        return vehicle.image.url if vehicle else ""

    @property
    def picture(self):
        """Its picture or its first vehicle's, else the first photo of a community on its
        way (a URL, or "")."""
        if self.header_image:
            return self.header_image
        for stop in self.stops.all():
            if stop.community_id:
                photo = next(iter(stop.community.photos.all()), None)
                if photo and photo.image:
                    return photo.image.url
        return ""

    @property
    def travel_mode_icon(self):
        return self.MODE_ICONS.get(self.travel_mode, "fa-route")

    @property
    def is_ride(self):
        """Just a lift from A to B: two stops, neither with a host, looking for travellers."""
        stops = list(self.stops.all())
        return self.open_to_join and len(stops) == 2 and not any(stop.community_id for stop in stops)

    # ── When ────────────────────────────────────────────────────────
    @property
    def is_published(self):
        return self.published_at is not None

    @property
    def is_idea(self):
        """No dates yet: someone looking for companions, a vehicle or a route."""
        return self.starts_on is None and self.ends_on is None

    @property
    def is_upcoming(self):
        return self.starts_on is not None and self.starts_on > timezone.localdate()

    @property
    def is_on_the_road(self):
        today = timezone.localdate()
        return (
            self.starts_on is not None and self.starts_on <= today
            and (self.ends_on is None or self.ends_on >= today)
        )

    @property
    def is_over(self):
        return self.ends_on is not None and self.ends_on < timezone.localdate()

    @property
    def is_current(self):
        return self.archived_at is None and not self.is_over

    def touch(self, save=True):
        """Mark the tour as up to date (an edit or a confirmation)."""
        self.updated_at = timezone.now()
        self.stale_reminder_sent_at = None
        if self.archived_at and not self.is_over:
            self.archived_at = None
        if save:
            self.save(update_fields=["updated_at", "stale_reminder_sent_at", "archived_at"])

    # ── Who may do what ─────────────────────────────────────────────
    def can_edit(self, user):
        return user.is_authenticated and (user.is_staff or self.is_organiser(user))

    def is_organiser(self, user):
        """The organiser matches are addressed to, or one they shared the role with."""
        if not user.is_authenticated:
            return False
        if user.pk == self.organiser_id:
            return True
        return self.travellers.counted().filter(user=user, is_organiser=True).exists()

    def organisers(self):
        """Everyone who organises it: the one matches are addressed to first."""
        users = [t.user for t in self.travellers.counted().filter(is_organiser=True).select_related("user")]
        return sorted(users, key=lambda user: user.pk != self.organiser_id)

    def make_organiser(self, traveller):
        """Share the role with a traveller on the tour."""
        traveller.is_organiser = True
        traveller.save(update_fields=["is_organiser"])

    def hand_over(self, traveller):
        """Make another organiser the one matches are addressed to. The open join
        requests, invitations and tour visits move to them; the one before stays an
        organiser."""
        from gift_economy.matches.models import Match

        before = self.organiser
        with transaction.atomic():
            self.make_organiser(traveller)
            self.organiser = traveller.user
            self.save(update_fields=["organiser"])
            if before is None:
                return
            open_ = [Match.STATUS_PENDING, Match.STATUS_COUNTER, Match.STATUS_ACCEPTED]
            # Not their own join request, which stays with the one before
            ours = self.matches.filter(status__in=open_).exclude(from_user=traveller.user).exclude(recipient=traveller.user)
            # Join requests come to the organiser, invitations come from them
            ours.filter(recipient=before, traveller__user=models.F("from_user")).update(recipient=traveller.user)
            ours.filter(from_user=before, traveller__user=models.F("recipient")).update(from_user=traveller.user)
            Match.objects.filter(tour_stop__tour=self, from_user=before, status__in=open_).update(from_user=traveller.user)
        # Who is a companion on each visit follows from who asked
        from .visits import sync_visits

        sync_visits(self)

    def can_view(self, user):
        if self._can_view(user):
            return True
        # The hosts it asked
        return user.is_authenticated and self.stops.filter(visit_match__recipient=user).exists()

    def _can_view(self, user):
        """A draft only for its organisers. A personal tour that is not listed only for
        its traveller and staff; the hosts it asks may see it too (can_view)."""
        if self.can_edit(user):
            return True
        return self.is_published and self.listed

    # ── The route ───────────────────────────────────────────────────
    def ordered_stops(self):
        return list(self.stops.all())

    def legs(self, stops=None):
        """The ways between the stops, with about how far each is."""
        stops = self.ordered_stops() if stops is None else stops
        legs = []
        for index, (start, end) in enumerate(zip(stops, stops[1:])):
            a, b = start.public_place()[1], end.public_place()[1]
            km = round(distance_km(a, b) * ROAD_FACTOR) if a is not None and b is not None else None
            legs.append(Leg(index, start, end, km))
        return legs

    def public_start(self):
        """(name, point) where it starts, as everyone sees it; ("", None) without stops."""
        for stop in self.stops.all():
            name, point = stop.public_place()
            if point is not None:
                return name, point
        return "", None

    # ── Who travels, and where there is room ────────────────────────
    # Leg i runs from stop i to stop i+1; a traveller
    # or vehicle without a first or last stop is on from the start or until the end.
    def counted_travellers(self):
        """The travellers who are on the tour: the organiser, or asked or invited and
        accepted."""
        return [t for t in self.travellers.select_related("user", "match") if t.is_counted]

    def stretch(self, from_stop, to_stop, stops=None):
        """(first, last) leg index between two stops (stops or pks; None for the start
        or the end). None if there is no leg in between."""
        stops = self.ordered_stops() if stops is None else stops
        if len(stops) < 2:
            return None
        index = {stop.pk: i for i, stop in enumerate(stops)}
        first = index.get(getattr(from_stop, "pk", from_stop), 0)
        last = index.get(getattr(to_stop, "pk", to_stop), len(stops) - 1) - 1
        return (first, last) if first <= last else None

    def room(self, stops=None, vehicles=None):
        """How many fit on each leg, in order: the seats of the vehicles on it plus one
        per vehicle with drivers, at most `max_people`; with no vehicle there,
        `max_people` (None: no limit). Without legs (an idea) one number."""
        stops = self.ordered_stops() if stops is None else stops
        vehicles = list(self.vehicles.all()) if vehicles is None else vehicles
        n = max(len(stops) - 1, 1)
        room = []
        for i in range(n):
            on = [v for v in vehicles if self._on_leg(v, i, stops, n)]
            seats = sum(v.places for v in on) if on else None
            if self.max_people is not None:
                seats = self.max_people if seats is None else min(seats, self.max_people)
            room.append(seats)
        return room

    def _on_leg(self, row, i, stops, n):
        """Whether a traveller or vehicle (with from_stop and to_stop) is on leg i."""
        first, last = self.stretch(row.from_stop_id, row.to_stop_id, stops) or (0, n - 1)
        return first <= i <= last

    def free_places(self, stops=None, travellers=None, exclude=None):
        """Free places on each leg, in order: its room minus the people of the counted
        travellers on it (None if there is no limit). Without legs (an idea) one number."""
        stops = self.ordered_stops() if stops is None else stops
        travellers = self.counted_travellers() if travellers is None else travellers
        n = max(len(stops) - 1, 1)
        free = self.room(stops)
        if all(places is None for places in free):
            return free
        for traveller in travellers:
            if exclude is not None and traveller.pk == exclude.pk:
                continue
            first, last = self.stretch(traveller.from_stop_id, traveller.to_stop_id, stops) or (0, n - 1)
            for i in range(first, last + 1):
                if free[i] is not None:
                    free[i] -= traveller.people
        return free

    def free_on(self, from_stop=None, to_stop=None, stops=None, exclude=None):
        """The fewest free places on the legs between two stops (None: no limit)."""
        stops = self.ordered_stops() if stops is None else stops
        free = self.free_places(stops=stops, exclude=exclude)
        first, last = self.stretch(from_stop, to_stop, stops) or (0, len(free) - 1)
        on = [places for places in free[first:last + 1] if places is not None]
        return max(min(on), 0) if on else None

    def fits(self, from_stop, to_stop, people, exclude=None):
        """Whether `people` more fit on every leg between the two stops."""
        free = self.free_on(from_stop, to_stop, exclude=exclude)
        return free is None or free >= people

    def present_at(self, stop):
        """The counted travellers at a stop's stay (not who only rides past it)."""
        stops = self.ordered_stops()
        index = {s.pk: i for i, s in enumerate(stops)}
        at = index[stop.pk]
        return [
            t for t in self.counted_travellers()
            if index.get(t.from_stop_id, 0) <= at <= index.get(t.to_stop_id, len(stops) - 1)
            and not t.ride_only
        ]

    # ── What it still looks for (gifts.Listing.tour) ────────────────
    def needs(self):
        """Its needs, in the order they were entered."""
        return self.listings.filter(type="wish").select_related("skill").prefetch_related(
            "contributions__match__from_user",
        ).order_by("order", "created_at")

    def team_skill_ids(self):
        """The skills the counted travellers offer."""
        from gift_economy.gifts.models import Listing

        people = [traveller.user_id for traveller in self.counted_travellers()]
        return set(
            Listing.objects.filter(owner__in=people, community=None, type=Listing.TYPE_OFFER, skill__isnull=False)
            .exclude(available=False).values_list("skill_id", flat=True)
        )

    # ── References about the whole group (gift_economy.references) ──
    # Hosts and others who met the group write about it, saying who of it was there.
    # References about single travellers stay on their profiles.
    reference_subject = True

    def get_reference_kind(self):
        return _("Tour"), "fa-route", "bg-purple"

    def get_reference_people(self):
        """Who can be named as having been there: everyone on the tour."""
        return [traveller.user for traveller in self.counted_travellers()]

    def get_reference_visits(self):
        """The stays someone writing about the group can say they met it at: the agreed
        tour visits, as (match, "stop · community")."""
        from gift_economy.matches.models import Match

        visits = []
        for stop in self.stops.filter(visit_match__status=Match.STATUS_ACCEPTED).select_related(
            "visit_match", "event", "community",
        ):
            label = f"{stop.event.title} · {stop.community.name}" if stop.event_id else stop.community.name
            visits.append((stop.visit_match, label))
        return visits

    def can_be_referenced_by(self, user):
        """Not by its own travellers: they write about the hosts and about each other."""
        return not any(traveller.user_id == user.pk for traveller in self.counted_travellers())

    # ── As what a join request is about (gift_economy.matches) ──────
    def get_match_owner(self):
        return self.organiser

    def get_match_display_name(self):
        return self.title

    def get_match_location(self):
        first = next(iter(self.stops.all()), None)
        name, point = first.public_place() if first else ("", None)
        return self.title, name, point

    # The route only goes through places everyone may see (rebuild_route)
    place_is_public = True

    @property
    def place_seed(self):
        return self.pk

    def get_match_icon(self):
        return self.travel_mode_icon

    def get_match_kind(self):
        return _("Join request"), "fa-route", "bg-purple"

    def get_match_verb(self, own=True):
        return _("asked to join")

    def get_match_request_text(self):
        return _("%(actor)s asked to join your tour: %(title)s")

    def get_match_summary(self, match):
        traveller = getattr(match, "traveller", None)
        return traveller.get_match_summary(match) if traveller is not None else ""

    # The stretch is changed on the join page, not with a counter-proposal
    match_counter = False

    def can_answer_match(self, user, match):
        """Every organiser answers a join request. An invitation only the one invited."""
        traveller = getattr(match, "traveller", None)
        return traveller is not None and not traveller.is_invitation and self.is_organiser(user)

    def get_match_answerers(self, match):
        """Who else is told of a new join request: the other organisers."""
        return self.organisers() if self.can_answer_match(match.recipient, match) else []

    @classmethod
    def matches_answered_by(cls, user):
        """The join requests `user` answers as one of the organisers (a Q on Match)."""
        from django.contrib.contenttypes.models import ContentType

        organised = Traveller.objects.counted().filter(user=user, is_organiser=True).values_list("tour_id", flat=True)
        return models.Q(
            content_type=ContentType.objects.get_for_model(cls),
            object_id__in=[str(pk) for pk in organised],
            traveller__user=models.F("from_user"),
        )

    def match_accept_error(self, match):
        """Why a join request can't be accepted (no room left on its stretch), or "".
        Called inside the transaction that accepts it; locks the tour, so two requests
        can't take the last place."""
        Tour.objects.select_for_update().filter(pk=self.pk).first()
        traveller = getattr(match, "traveller", None)
        if traveller is None:
            return ""
        if not self.fits(traveller.from_stop_id, traveller.to_stop_id, traveller.people, exclude=traveller):
            return _("There is no room left on this stretch any more.")
        return ""

    def rebuild_route(self, save=True):
        """Dates, countries, route line and distance from the stops. The line goes
        through the points everyone may see (a private community's rough place), so it
        gives no door away."""
        stops = self.ordered_stops()
        points = [point for _name, point in (stop.public_place() for stop in stops) if point is not None]
        self.route = LineString([p.coords for p in points], srid=4326) if len(points) >= 2 else None
        self.start = points[0] if points else None
        if len(points) >= 2:
            total = sum(distance_km(a, b) for a, b in zip(points, points[1:]))
            self.distance_km = round(total * ROAD_FACTOR)
        else:
            self.distance_km = None

        days = [day for stop in stops for day in (stop.arrive_on, stop.leave_on) if day]
        self.starts_on = min(days) if days else None
        self.ends_on = max(days) if days else None

        countries = []
        for stop in stops:
            code = stop.country_code
            if code and code not in countries:
                countries.append(code)
        if countries:
            self.countries = countries
        if save:
            self.save(update_fields=["route", "start", "distance_km", "starts_on", "ends_on", "countries"])


class Stop(models.Model):
    """One place on a tour's route, in order: at an event, at a community (a stay with no
    event), or at another place, such as a meeting point, a town, or a gathering that is not
    on ecobasa. Never somebody's home. The event or community is the stop's host."""

    MODE_CHOICES = Tour.MODE_CHOICES

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="stops")
    order = models.PositiveSmallIntegerField(default=0)
    event = models.ForeignKey(
        Event, on_delete=models.SET_NULL, null=True, blank=True, related_name="tour_stops",
        verbose_name=_("Event"),
    )
    community = models.ForeignKey(
        Community, on_delete=models.SET_NULL, null=True, blank=True, related_name="tour_stops",
        verbose_name=_("Community"),
    )
    # Only for another place: public as entered
    name = models.CharField(_("Place"), max_length=255, blank=True)
    location = models.PointField(_("Geo Location"), null=True, blank=True, geography=True)
    country = CountryField(_("Country"), null=True, blank=True)
    arrive_on = models.DateField(_("Arrive"), null=True, blank=True)
    leave_on = models.DateField(_("Leave"), null=True, blank=True)
    leave_at = models.TimeField(_("Setting off at"), null=True, blank=True)
    flexible = models.BooleanField(_("Give or take a few days"), default=False)
    note = models.TextField(_("What we plan here"), blank=True)
    # If the way on from here goes another way (a ferry, a train)
    onward_mode = models.CharField(_("Going on by"), max_length=20, choices=MODE_CHOICES, blank=True)
    # The tour visit: the group's stay, asked of the host once for the whole group. Its status is
    # where the host stands
    visit_match = models.OneToOneField(
        "matches.Match", on_delete=models.SET_NULL, null=True, blank=True, related_name="tour_stop",
    )

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("Stop")
        verbose_name_plural = _("Stops")
        constraints = [
            # Deferred, so two stops can swap places in one transaction
            models.UniqueConstraint(
                fields=["tour", "order"], name="one_stop_per_place_in_tour",
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]

    def __str__(self):
        return f"{self.order + 1}. {self.label}"

    def save(self, *args, **kwargs):
        if self.event_id:
            self.community_id = self.event.community_id
        if self.community_id:
            self.name, self.location, self.country = "", None, None
        super().save(*args, **kwargs)

    # ── What it is ──────────────────────────────────────────────────
    @property
    def host(self):
        """The event or community the tour stays with, if any."""
        return self.event or self.community

    @property
    def label(self):
        if self.event_id:
            return self.event.title
        if self.community_id:
            return self.community.name
        return self.name

    @property
    def icon(self):
        if self.event_id:
            return self.event.kind_icon
        if self.community_id:
            return self.community.get_type_icon()
        return "fa-location-dot"

    @property
    def country_code(self):
        country = self.community.country if self.community_id else self.country
        return country.code if country else None

    # ── Where it is, and who may know ───────────────────────────────
    def public_place(self):
        """(name, point) as everyone sees it: a community's (also for an event there)
        only roughly unless it is public; another place as it was entered."""
        if self.community_id:
            return self.community.rough_place()
        return self.name, self.location

    def place_for(self, user):
        """(name, point) as `user` sees it."""
        if self.community_id:
            return self.community.place_for(user)
        return self.name, self.location

    # ── The tour visit: where the host stands ───────────────────────
    HOST_NOT_ASKED = "not_asked"
    HOST_ASKED = "asked"
    HOST_AGREED = "agreed"
    HOST_OTHER_DAYS = "other_days"
    HOST_DECLINED = "declined"
    HOST_COMING = "coming"
    HOST_LABELS = {
        HOST_NOT_ASKED: (pgettext_lazy("host status", "Not asked yet"), "fa-solid fa-ban", "text-red"),
        HOST_ASKED: (pgettext_lazy("host status", "Asked"), "fa-solid fa-hourglass-half", "text-yellow"),
        HOST_AGREED: (pgettext_lazy("host status", "Agreed"), "fa-solid fa-circle-check", "text-green"),
        HOST_OTHER_DAYS: (pgettext_lazy("host status", "Other days proposed"), "fa-solid fa-calendar-days", "text-yellow"),
        HOST_DECLINED: (pgettext_lazy("host status", "Declined"), "fa-solid fa-circle-xmark", "text-red"),
        HOST_COMING: (pgettext_lazy("host status", "We're coming"), "fa-solid fa-people-group", "text-green"),
    }

    @property
    def joins_open_event(self):
        """An event where people just come: the tour says it is coming, nobody answers."""
        return bool(self.event_id and self.event.is_open)

    @property
    def host_status(self):
        """Where the host stands, "" without a host."""
        from gift_economy.matches.models import Match

        if not self.community_id or self.host.get_match_owner() is None:
            return ""
        match = self.visit_match
        if match is None or match.status == Match.STATUS_WITHDRAWN:
            return self.HOST_NOT_ASKED
        if match.is_coming:
            return self.HOST_COMING
        return {
            Match.STATUS_ACCEPTED: self.HOST_AGREED,
            Match.STATUS_COUNTER: self.HOST_OTHER_DAYS,
            Match.STATUS_DECLINED: self.HOST_DECLINED,
        }.get(match.status, self.HOST_ASKED)

    @property
    def host_status_label(self):
        return self.HOST_LABELS.get(self.host_status, ("", "", ""))

    @property
    def can_ask_host(self):
        """Whether the organisers can ask (again): not yet, or after a no or a withdrawal."""
        return self.host_status in (self.HOST_NOT_ASKED, self.HOST_DECLINED)

    def group(self):
        """The counted travellers at this stop's stay: who the host is asked to take."""
        return self.tour.present_at(self)

    def group_people(self, group=None):
        return sum(t.people for t in (self.group() if group is None else group))

    # ── As what a tour visit is attached to (gift_economy.matches) ──
    match_attachment_template = "tours/_visit_summary.html"

    def visit_people(self):
        """Who comes on the tour visit, each with the skills they offer, for the host:
        [(user, [skill listings])]. The one who asked first."""
        from gift_economy.gifts.models import Listing

        match = self.visit_match
        if match is None:
            return []
        people = [match.from_user, *match.stay_details.companions.all()]
        offers = {}
        for offer in (
            Listing.objects.open().filter(owner__in=people, community=None, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
            .exclude(available=False).select_related("skill")
        ):
            offers.setdefault(offer.owner_id, []).append(offer)
        return [(person, sorted(offers.get(person.pk, []), key=lambda l: l.display_title)) for person in people]

    def get_match_kind(self):
        return _("Tour visit"), "fa-route", "bg-green"

    def get_match_verb(self):
        return _("asked to host their tour at")

    # After the visit the host writes about the group, or about one of them
    def get_reference_group(self):
        return self.tour

    def get_reference_present(self, match):
        return [match.from_user, *match.stay_details.companions.all()]

    def get_match_summary(self, match):
        people = match.people
        return _("%(tour)s · %(people)s") % {
            "tour": self.tour.title,
            "people": ngettext("%(n)s person", "%(n)s people", people) % {"n": people},
        }


class TravellerQuerySet(models.QuerySet):
    def counted(self):
        """Those on the tour: without a match (the organiser), or accepted."""
        from gift_economy.matches.models import Match

        return self.filter(models.Q(match=None) | models.Q(match__status=Match.STATUS_ACCEPTED))


class Traveller(models.Model):
    """Someone on a tour from one stop to another, both included (None: from the start,
    until the end). The organiser is a traveller too. Others come through a match with
    the tour as target: a join request they made, or an invitation an organiser sent
    them. They count once it is accepted."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="travellers")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tour_travels")
    match = models.OneToOneField(
        "matches.Match", on_delete=models.CASCADE, null=True, blank=True, related_name="traveller",
    )
    from_stop = models.ForeignKey(
        Stop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("From"),
    )
    to_stop = models.ForeignKey(
        Stop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("To"),
    )
    people = models.PositiveSmallIntegerField(
        _("How many are you?"), default=1, help_text=_("You and whoever comes with you, children too."),
    )
    ride_only = models.BooleanField(_("I only need the ride"), default=False)
    pickup_name = models.CharField(_("Pick me up at"), max_length=255, blank=True)
    pickup_point = models.PointField(null=True, blank=True, geography=True)
    dropoff_name = models.CharField(_("Drop me at"), max_length=255, blank=True)
    dropoff_point = models.PointField(null=True, blank=True, geography=True)
    is_organiser = models.BooleanField(_("Organiser"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TravellerQuerySet.as_manager()

    class Meta:
        ordering = ["-is_organiser", "created_at", "pk"]
        verbose_name = _("Traveller")
        verbose_name_plural = _("Travellers")

    def __str__(self):
        return f"{self.user} on {self.tour}"

    @property
    def is_counted(self):
        from gift_economy.matches.models import Match

        return self.match_id is None or self.match.status == Match.STATUS_ACCEPTED

    @property
    def is_invitation(self):
        """An organiser invited them, rather than they asked to join."""
        return self.match_id is not None and self.match.recipient_id == self.user_id

    # ── As what a join request or invitation is attached to (gift_economy.matches) ──
    match_attachment_template = "tours/_match_summary.html"

    def get_match_kind(self):
        if self.is_invitation:
            return _("Invitation"), "fa-envelope-open-text", "bg-purple"
        return self.tour.get_match_kind()

    def get_match_verb(self):
        if self.is_invitation:
            return _("sent an invitation to travel along on")
        return self.tour.get_match_verb()

    def get_match_request_text(self):
        if self.is_invitation:
            return _("%(actor)s invited you to travel along: %(title)s")
        return self.tour.get_match_request_text()

    def get_match_summary(self, match):
        """The stretch and how many, for the match emails."""
        start, end = self.ends()
        stretch = f"{start.label} → {end.label}" if start and end and not self.whole_route else str(_("the whole route"))
        people = ngettext("%(n)s person", "%(n)s people", self.people) % {"n": self.people}
        return f"{stretch} · {people}"

    def ends(self, stops=None):
        """(first stop, last stop) of the stretch, filled in from the route."""
        stops = self.tour.ordered_stops() if stops is None else stops
        start = self.from_stop or (stops[0] if stops else None)
        end = self.to_stop or (stops[-1] if stops else None)
        return start, end

    @property
    def whole_route(self):
        return self.from_stop_id is None and self.to_stop_id is None

    def pickup_place(self, viewer=None):
        """(name, point) of where they get on between stops: roughly until the request
        is accepted, except to the one who asked (as Match.places_shown)."""
        return self._place(self.pickup_name, self.pickup_point, viewer)

    def dropoff_place(self, viewer=None):
        return self._place(self.dropoff_name, self.dropoff_point, viewer)

    def _place(self, name, point, viewer):
        from users.places import approximate, town

        if not name and point is None:
            return "", None
        if viewer == self.user or self.is_counted:
            return name, point
        return town(name), approximate(point, self.user_id)


class Vehicle(models.Model):
    """A vehicle the tour travels in: it gives the tour its places, on the whole route or
    part of it. Optional: tours by bike, train, thumb or on foot are normal. Not a gift
    listing: a vehicle offered in the gifts is given away or lent, and one borrowed for a
    tour is not linked to its listing yet."""

    tour = models.ForeignKey(Tour, on_delete=models.CASCADE, related_name="vehicles")
    label = models.CharField(_("What vehicle?"), max_length=100)
    image = models.ImageField(_("Picture"), upload_to="tours-vehicles", null=True, blank=True)
    # Who may drive it; one of them drives at a time
    drivers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="+", verbose_name=_("Drivers"),
    )
    seats = models.PositiveSmallIntegerField(_("Seats besides the driver"), default=0)
    sleeps = models.PositiveSmallIntegerField(_("Sleeping places"), null=True, blank=True)
    # Free text on purpose, no volume maths
    note = models.CharField(_("What fits in and on it, how comfy it is"), max_length=255, blank=True)
    needs_driver = models.BooleanField(_("Still needs a driver"), default=False)
    others_may_drive = models.BooleanField(_("Others may drive too"), default=False)
    # Only for part of the route (None: from the start, until the end)
    from_stop = models.ForeignKey(
        Stop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("From"),
    )
    to_stop = models.ForeignKey(
        Stop, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("To"),
    )

    class Meta:
        ordering = ["pk"]
        verbose_name = _("Vehicle")
        verbose_name_plural = _("Vehicles")

    def __str__(self):
        return self.label

    @property
    def places(self):
        """How many people it takes: its seats and the driver's seat, if someone drives it
        (the other drivers sit in the seats)."""
        return self.seats + (1 if self.drivers.all() else 0)

    @property
    def whole_route(self):
        return self.from_stop_id is None and self.to_stop_id is None


def append_stop(stop):
    """Add `stop` at the end of its tour's route."""
    last = stop.tour.stops.order_by("-order").values_list("order", flat=True).first()
    stop.order = 0 if last is None else last + 1
    stop.save()
    stop.tour.rebuild_route()


def insert_stop(stop, position):
    """Add `stop` to its tour's route at `position` (0 is the start), moving the stops
    from there on one place on."""
    tour = stop.tour
    with transaction.atomic():
        count = tour.stops.count()
        position = max(0, min(position, count))
        # The constraint on the order is deferred, so they can move up in one go
        tour.stops.filter(order__gte=position).update(order=models.F("order") + 1)
        stop.order = position
        stop.save()
    tour.rebuild_route()


def set_order(tour, stops):
    """Put the tour's stops in the order of `stops` (all of them)."""
    with transaction.atomic():
        for order, stop in enumerate(stops):
            Stop.objects.filter(pk=stop.pk, tour=tour).update(order=order)
    tour.rebuild_route()


def move_stop(stop, step):
    """Swap `stop` with the one before (step -1) or after (step 1) it."""
    stops = stop.tour.ordered_stops()
    index = next(i for i, s in enumerate(stops) if s.pk == stop.pk)
    other_index = index + step
    if not 0 <= other_index < len(stops):
        return
    other = stops[other_index]
    with transaction.atomic():
        stop.order, other.order = other.order, stop.order
        Stop.objects.filter(pk=stop.pk).update(order=stop.order)
        Stop.objects.filter(pk=other.pk).update(order=other.order)
    stop.tour.rebuild_route()


def remove_stop(stop):
    """Delete `stop` and close the gap it leaves."""
    tour = stop.tour
    with transaction.atomic():
        stop.delete()
        for order, rest in enumerate(tour.stops.order_by("order", "pk")):
            if rest.order != order:
                Stop.objects.filter(pk=rest.pk).update(order=order)
    tour.rebuild_route()
