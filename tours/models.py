from collections import namedtuple

from django.conf import settings
from django.contrib.gis.db import models
from django.contrib.gis.geos import LineString
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField

from communities.models import Community
from events.models import Event
from gift_economy.matches.matching import distance_km

# Straight distance times this is about the way on roads (docs/community-tours-plan.md, D8)
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
    RESERVED_SLUGS = ("new", "api")

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
    distance_km = models.PositiveIntegerField(_("About how many km"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    # Bumped whenever the tour or its stops change, or an organiser confirms it is still
    # current. Not auto_now: archiving must not make a tour look fresh.
    updated_at = models.DateTimeField(_("Updated"), default=timezone.now)
    stale_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(_("Archived"), null=True, blank=True)

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
    def travel_mode_icon(self):
        return self.MODE_ICONS.get(self.travel_mode, "fa-route")

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
        return user.is_authenticated and (user.is_staff or user == self.organiser)

    def can_view(self, user):
        """A draft only for its organisers. A personal tour that is not listed only for
        its traveller and staff; the hosts it asks and the givers and receivers of its
        deliveries come with those features (docs/community-tours-plan.md, 5.5 rule 8)."""
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

    def rebuild_route(self, save=True):
        """Dates, countries, route line and distance from the stops. The line goes
        through the points everyone may see (a private community's rough place), so it
        gives no door away."""
        stops = self.ordered_stops()
        points = [point for _name, point in (stop.public_place() for stop in stops) if point is not None]
        self.route = LineString([p.coords for p in points], srid=4326) if len(points) >= 2 else None
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
            self.save(update_fields=["route", "distance_km", "starts_on", "ends_on", "countries"])


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


def append_stop(stop):
    """Add `stop` at the end of its tour's route."""
    last = stop.tour.stops.order_by("-order").values_list("order", flat=True).first()
    stop.order = 0 if last is None else last + 1
    stop.save()
    stop.tour.rebuild_route()


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
