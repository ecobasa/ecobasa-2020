from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _, ngettext
from django_countries.fields import CountryField

from communities.models import Community, language_name
from users.places import approximate, town

from . import kinds


class EventQuerySet(models.QuerySet):
    def current(self):
        """Not archived and not over yet. Events without an end date are ongoing."""
        today = timezone.localdate()
        return self.filter(archived_at=None).filter(models.Q(ends_on=None) | models.Q(ends_on__gte=today))

    def asking_to_join(self):
        """Those where who can't just come asks to join (kinds.ASK_TO_JOIN)."""
        return self.filter(kind__in=kinds.ASK_TO_JOIN)


class Event(models.Model):
    """A time and a place where people and things come together. Its kind gives it its
    word, icon and starting settings (kinds.py):

    - a project: something a community wants to realise with help from outside, e.g.
      "Build a rocket stove, March–April": what it needs (volunteers with skills,
      materials, tools, knowledge) and what the community provides in return;
    - a community event: something a community invites to, e.g. an open day, a workshop
      or a festival;
    - a gift-circle: people meet in a circle and say what they wish for and what they
      can give.

    Dated events end with their end date; ongoing ones have none and stay current as long
    as someone keeps them up to date (see freshness.py). People take part through a match:
    one the host answers, or, on an open event, one that needs no answer.

    Hosted by a community, a person or a tour (exactly one of them; its kind says which it
    allows, kinds.HOSTS). Who answers for an event, where it is and who may edit it is
    asked of the event (`manager`, `place`, `can_edit`). It happens at its community's
    place, at a place of its own (`location`), or online.
    """

    KIND_PROJECT = kinds.PROJECT
    KIND_COMMUNITY_EVENT = kinds.COMMUNITY_EVENT
    KIND_GIFT_CIRCLE = kinds.GIFT_CIRCLE

    # Not usable as a slug: they are paths beside an event's page
    RESERVED_SLUGS = ("new",)

    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, null=True, blank=True, related_name="events",
        verbose_name=_("Community"),
    )
    # Another host than a community: a person, or a tour (its organisers). A string
    # reference, so this app imports nothing from tours
    host_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="hosted_events", verbose_name=_("Host"),
    )
    host_tour = models.ForeignKey(
        "tours.Tour", on_delete=models.CASCADE, null=True, blank=True, related_name="hosted_events",
        verbose_name=_("Tour"),
    )
    kind = models.CharField(_("Kind"), max_length=20, choices=kinds.CHOICES, default=kinds.PROJECT)
    # Set from the title once, unique within the community (or among its kind, if its kind
    # has an address of its own): its address stays when the title changes
    slug = models.SlugField(_("Slug"), max_length=255, blank=True)
    title = models.CharField(_("Title"), max_length=255)
    description = models.TextField(_("Description"), blank=True)
    image = models.ImageField(_('image'), upload_to='events-images', null=True, blank=True)
    starts_on = models.DateField(_("From"), null=True, blank=True)
    ends_on = models.DateField(
        _("Until"), null=True, blank=True,
        help_text=_("Leave empty if it is ongoing, without an end date."),
    )
    # Times of day, e.g. an open day from 14:00 to 18:00
    starts_at = models.TimeField(_("Starts at"), null=True, blank=True)
    ends_at = models.TimeField(_("Ends at"), null=True, blank=True)
    # People just come and say so; otherwise they ask first and the host answers
    is_open = models.BooleanField(
        _("Open event: people can just come"), default=False,
        help_text=_("Otherwise people ask first and you answer, like for a volunteer stay."),
    )
    food_provided = models.BooleanField(_("Food provided"), default=False)
    bed_provided = models.BooleanField(_("Bed provided"), default=False)
    provided_note = models.CharField(
        _("What else you provide"), max_length=255, blank=True,
        help_text=_("e.g. a tent spot, tools, a workshop, rides from the train station"),
    )
    volunteers_wanted = models.PositiveSmallIntegerField(
        _("How many volunteers at the same time?"), null=True, blank=True,
    )
    max_people = models.PositiveSmallIntegerField(_("How many people can come?"), null=True, blank=True)
    potluck_note = models.CharField(
        _("Potluck"), max_length=200, blank=True,
        help_text=_("What people could bring to share. Leave it empty if there is no potluck."),
    )
    # A place of its own, e.g. a park or a café; otherwise its community's. Everyone but
    # who comes sees it roughly (rough_place). Online: the town it is for people around, if
    # any (area)
    location_name = models.CharField(_("Place"), max_length=255, blank=True)
    location = models.PointField(_("Geo Location"), null=True, blank=True, geography=True)
    country = CountryField(_("Country"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Bumped whenever the event or its needs change, or the ambassador confirms it is
    # still current. Not auto_now: archiving must not make an event look fresh.
    updated_at = models.DateTimeField(_("Updated"), default=timezone.now)
    stale_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(_("Archived"), null=True, blank=True)
    # Online: no place; the video link goes to who comes. Its times are in `timezone`
    # (last: the field hides the timezone module in this class body)
    is_online = models.BooleanField(_("Online, as a video call"), default=False)
    video_url = models.URLField(_("Video link"), blank=True)
    # When the video call went to who comes, an hour before
    video_call_mailed_at = models.DateTimeField(null=True, blank=True)
    # What is spoken in the call (anyone anywhere may come, so it matters which); codes
    # from Django's LANG_INFO, as a community's
    languages = ArrayField(models.CharField(max_length=12), verbose_name=_("Languages"), default=list, blank=True)
    timezone = models.CharField(_("Timezone"), max_length=64, blank=True)
    # The one it follows on, planned by someone who came to that one
    previous = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="next_ones",
    )
    matches = GenericRelation("matches.Match")

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        constraints = [
            models.UniqueConstraint(fields=["community", "slug"], name="one_event_slug_per_community"),
            models.UniqueConstraint(
                fields=["kind", "slug"], name="one_event_slug_per_own_address",
                condition=Q(kind__in=list(kinds.ADDRESSES)),
            ),
            models.CheckConstraint(
                name="event_has_one_host",
                check=Q(community__isnull=False, host_user=None, host_tour=None)
                | Q(community=None, host_user__isnull=False, host_tour=None)
                | Q(community=None, host_user=None, host_tour__isnull=False),
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Kinds on one day are never ongoing: they end the day they start
        if self.kind in kinds.ONE_DAY and self.starts_on:
            self.ends_on = self.starts_on
        # Also when its kind changed to one with an address of its own, where the slug
        # may be taken
        if not self.slug or (kwargs.get("update_fields") is None and self._slug_taken()):
            self.slug = self._free_slug()
        super().save(*args, **kwargs)

    def _same_address(self):
        """The events whose slugs this one's must differ from."""
        if self.kind in kinds.ADDRESSES:
            events = Event.objects.filter(kind=self.kind)
        else:
            events = Event.objects.filter(community_id=self.community_id)
        return events.exclude(pk=self.pk) if self.pk else events

    def _slug_taken(self):
        return self._same_address().filter(slug=self.slug).exists()

    def _free_slug(self):
        base = slugify(self.title)[:240] or "event"
        taken = set(self._same_address().values_list("slug", flat=True))
        taken.update(self.RESERVED_SLUGS)
        slug, suffix = base, 1
        while slug in taken:
            suffix += 1
            slug = f"{base}-{suffix}"
        return slug

    def url(self, name="detail", *args):
        """The address of one of its pages: under its kind's own address, else under its
        community's."""
        if self.kind in kinds.ADDRESSES:
            return reverse(f"events:{self.kind}_{name}", args=[self.slug, *args])
        return reverse(f"events:{name}", args=[self.community.slug, self.slug, *args])

    def get_absolute_url(self):
        return self.url()

    # ── Its kind: a word and an icon ────────────────────────────────
    @property
    def kind_label(self):
        return self.get_kind_display()

    @property
    def kind_icon(self):
        return kinds.ICONS[self.kind]

    @property
    def kind_colour(self):
        return kinds.COLOURS[self.kind]

    @property
    def kind_pin(self):
        """(the icon's code point, colour) for a map."""
        return kinds.PINS[self.kind]

    @property
    def texts(self):
        """The sentences that name its kind ("This project has ended.")."""
        return kinds.TEXTS[self.kind]

    # ── When ────────────────────────────────────────────────────────
    def tools(self):
        """(url, label, icon) of its kind's add-on pages for whoever may edit it."""
        return [(reverse(name, args=[self.slug]), label, icon) for name, label, icon in kinds.TOOLS.get(self.kind, ())]

    @property
    def is_ongoing(self):
        return self.ends_on is None

    @property
    def is_over(self):
        return self.ends_on is not None and self.ends_on < timezone.localdate()

    @property
    def zone(self):
        """The timezone of an online event's hours (the server's while none is set); None
        at a place, where they are local."""
        if not self.is_online:
            return None
        try:
            return ZoneInfo(self.timezone or settings.TIME_ZONE)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(settings.TIME_ZONE)

    @property
    def zone_city(self):
        """"Berlin" of Europe/Berlin, to say "19:00 Berlin time"; empty at a place."""
        zone = self.zone
        return zone.key.rsplit("/", 1)[-1].replace("_", " ") if zone else ""

    @property
    def zoned_hours(self):
        """(start, end) of an online event's (first) day's hours in its timezone, so each
        reader's page can also show them in their own (end None without an end); None without
        them."""
        zone = self.zone
        if zone is None or not (self.starts_on and self.starts_at):
            return None
        start = datetime.combine(self.starts_on, self.starts_at, tzinfo=zone)
        if not self.ends_at:
            return start, None
        # The hours of its first day; past midnight they end the next day
        end = datetime.combine(self.starts_on, self.ends_at, tzinfo=zone)
        return start, end if end > start else end + timedelta(days=1)

    @property
    def language_names(self):
        """"German, English": what is spoken in it, in the current language."""
        return ", ".join(filter(None, (language_name(code) for code in self.languages)))

    @property
    def is_current(self):
        return self.archived_at is None and not self.is_over

    @property
    def is_one_day(self):
        return self.ends_on is not None and (self.starts_on or self.ends_on) == self.ends_on

    def touch(self, save=True):
        """Mark the event as up to date (an edit or a confirmation)."""
        self.updated_at = timezone.now()
        self.stale_reminder_sent_at = None
        if self.archived_at and not self.is_over:
            self.archived_at = None
        if save:
            self.save(update_fields=["updated_at", "stale_reminder_sent_at", "archived_at"])

    def stale_since(self):
        return self.updated_at + timedelta(days=settings.EVENT_STALE_DAYS)

    # ── Who hosts it and answers for it, where it is, who may edit ──
    @property
    def host(self):
        """The community, person or tour that invites to it."""
        return self.community or self.host_user or self.host_tour

    @property
    def host_type(self):
        """kinds.HOST_COMMUNITY, HOST_PERSON or HOST_TOUR."""
        if self.community_id:
            return kinds.HOST_COMMUNITY
        if self.host_user_id:
            return kinds.HOST_PERSON
        return kinds.HOST_TOUR

    @property
    def host_name(self):
        if self.community_id:
            return self.community.name
        if self.host_user_id:
            return self.host_user.name or self.host_user.username
        return self.host_tour.title

    @property
    def manager(self):
        """Who answers for it: matches are addressed to them."""
        if self.community_id:
            return self.community.ambassador
        if self.host_user_id:
            return self.host_user
        return self.host_tour.organiser

    @property
    def takes_needs(self):
        """Whether it lists needs and skills to learn: they are its community's wishes and
        offers in it."""
        return self.community_id is not None

    def can_edit(self, user):
        if not user.is_authenticated:
            return False
        if user.is_staff or user == self.manager:
            return True
        # A community's members, as they edit its page; a tour's organisers share the role
        if self.community_id:
            return self.community.can_edit(user)
        return bool(self.host_tour_id and self.host_tour.can_edit(user))

    @property
    def place(self):
        """Where it happens: something with a name, a rough place for everyone and an
        exact one for those who may know (rough_place, place_for). Itself if it has a
        place of its own, else its community; nothing online."""
        if self.is_online:
            return None
        if self.location is not None:
            return self
        return self.community

    @property
    def name(self):
        """Its name as a place."""
        return self.title

    @property
    def area(self):
        """Online: the town it is for people around; "" for anyone anywhere."""
        return town(self.location_name) if self.is_online and self.location is not None else ""

    def rough_place(self):
        """(name, point) as everyone sees it; ("", None) without a place. Online: its area."""
        if self.area:
            return self.area, approximate(self.location, self.place_seed)
        place = self.place
        if place is None:
            return "", None
        if place is not self:
            return place.rough_place()
        return town(self.location_name), approximate(self.location, self.place_seed)

    def place_for(self, user):
        """(name, point) as `user` sees it."""
        if self.is_online:
            return self.rough_place()
        place = self.place
        if place is not None and place is not self:
            return place.place_for(user)
        return (self.location_name, self.location) if self.shows_place_to(user) else self.rough_place()

    def shows_place_to(self, user):
        """Whether `user` sees its exact place: whoever may edit it, and who comes (an
        accepted match)."""
        place = self.place
        if place is not None and place is not self:
            return place.shows_place_to(user)
        if self.can_edit(user):
            return True
        if not user.is_authenticated:
            return False
        from gift_economy.matches.models import Match
        return self.matches.filter(from_user=user, status=Match.STATUS_ACCEPTED).exists()

    def people_coming(self):
        """How many come: everyone accepted, with whoever they bring, and the guests
        without an account (gift_circles.Guest)."""
        from gift_economy.matches.models import Match
        accepted = self.matches.filter(status=Match.STATUS_ACCEPTED).select_related("stay_details")
        return sum(match.people for match in accepted) + sum(guest.people for guest in self.guests.coming())

    def free_places(self):
        """How many more can come, None without a limit."""
        if not self.max_people:
            return None
        return max(0, self.max_people - self.people_coming())

    def takes_people(self, user=None):
        """Whether someone (or `user`) can offer help or say they come: it is current,
        somebody answers for it, it is not their own, and it isn't full."""
        return (
            self.is_current and self.manager is not None and user != self.manager
            and self.free_places() != 0
        )

    @property
    def asks_to_join(self):
        """Whether who can't just come asks to join in a few words, rather than offering
        help with its needs: nothing is needed but people (kinds.ASK_TO_JOIN)."""
        return self.kind in kinds.ASK_TO_JOIN

    def may_just_come(self, user):
        """Whether `user` comes without asking: it is open, it is their tour's, or they
        were invited (gift_circles.Invitation)."""
        if self.is_open:
            return True
        if not user.is_authenticated:
            return False
        return bool(
            self.host_tour_id and self.host_tour.travellers.counted().filter(user=user).exists()
        ) or self.invitations.filter(user=user).exists()

    # Its needs are the community's wishes in it, and what you can learn here its skill
    # offers in it (gifts.Listing.event). Both are listed only while it runs.
    def needs(self):
        return sorted((l for l in self.listings.all() if l.is_wish), key=lambda l: (l.order, l.created_at))

    def skills_to_learn(self):
        return sorted((l for l in self.listings.all() if l.is_offer and l.skill_id), key=lambda l: l.display_title)

    def open_needs(self):
        return [need for need in self.needs() if need.status == need.STATUS_OPEN]

    @property
    def provides_something(self):
        return bool(self.food_provided or self.bed_provided or self.provided_note or self.volunteers_wanted)

    # ── How it went: references about it (kinds.HOW_IT_WENT) ───────
    # Only where its kind tells how it went, as `can_be_referenced_by` says
    reference_subject = True

    @property
    def has_begun(self):
        return self.starts_on is not None and self.starts_on <= timezone.localdate()

    def can_be_referenced_by(self, user):
        """Who came or hosted it tells how it went, once it has begun."""
        if self.kind not in kinds.HOW_IT_WENT or not self.has_begun or not user.is_authenticated:
            return False
        return self.can_edit(user) or self.matches.filter(
            from_user=user, status=self.matches.model.STATUS_ACCEPTED,
        ).exists()

    def get_reference_kind(self):
        return self.kind_label, self.kind_icon, self.kind_colour

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.manager

    def get_match_display_name(self):
        return self.title

    def get_match_location(self):
        place = self.place
        if place is None:
            return self.title, "", None
        return place.name, place.location_name, place.location

    # Where it is, and who may know: its place's. A place of its own only roughly
    @property
    def place_seed(self):
        place = self.place
        if place is None or place is self:
            return f"event:{self.pk}"
        return place.place_seed

    @property
    def place_is_public(self):
        place = self.place
        if place is None:
            return True
        return False if place is self else place.place_is_public

    def get_match_icon(self):
        return self.kind_icon

    def get_match_kind(self):
        """What a match about it shows as its pill: (label, icon, colour)."""
        return self.kind_label, self.kind_icon, "bg-green"

    def get_match_verb(self):
        if self.asks_to_join:
            return _("asked to join")
        return _("offered to help with")

    def get_match_request_text(self):
        if self.asks_to_join:
            return self.texts["join_request"]
        return self.texts["help_request"]

    def get_match_stay_label(self):
        """What the days a match asks for are called: its kind where one asks to join (a
        gift-circle), else a stay."""
        return self.kind_label if self.asks_to_join else _("Proposed stay")

    def get_match_summary(self, match):
        """How many come, for the emails, where one asks to join."""
        if not self.asks_to_join:
            return ""
        return ngettext("%(n)s person", "%(n)s people", match.people) % {"n": match.people}

    @property
    def match_counter(self):
        """Where one asks to join, the host says yes or no: its day is its own."""
        return not self.asks_to_join

    @property
    def match_request_type(self):
        """Where its matches are listed in the dashboard: asking to join with the events one
        attends, help with the volunteer visits."""
        return "events" if self.asks_to_join else "volunteer"

    def match_accept_error(self, match):
        """Why it can't be accepted now: no room left for them."""
        free = self.free_places()
        if free is not None and match.people > free:
            return ngettext(
                "Only %(count)s more person can come.", "Only %(count)s more people can come.", free,
            ) % {"count": free}
        return ""

    def match_accepted(self, match, data=None):
        """Whoever was accepted comes."""
        from .signals import coming

        coming.send(sender=Event, event=self, user=match.from_user, match=match, data=None)
