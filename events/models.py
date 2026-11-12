from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from communities.models import Community

from . import kinds


class EventQuerySet(models.QuerySet):
    def current(self):
        """Not archived and not over yet. Events without an end date are ongoing."""
        today = timezone.localdate()
        return self.filter(archived_at=None).filter(models.Q(ends_on=None) | models.Q(ends_on__gte=today))


class Event(models.Model):
    """A time and a place where people and things come together. Its kind gives it its
    word, icon and starting settings (kinds.py):

    - a project: something a community wants to realise with help from outside, e.g.
      "Build a rocket stove, March–April": what it needs (volunteers with skills,
      materials, tools, knowledge) and what the community provides in return;
    - a community event: something a community invites to, e.g. an open day, a workshop
      or a festival.

    Dated events end with their end date; ongoing ones have none and stay current as long
    as someone keeps them up to date (see freshness.py). People take part through a match:
    one the host answers, or, on an open event, one that needs no answer.

    Hosted by a community for now. Who answers for an event, where it is and who may edit
    it is asked of the event (`manager`, `place`, `can_edit`), so another host changes
    this model only.
    """

    KIND_PROJECT = kinds.PROJECT
    KIND_COMMUNITY_EVENT = kinds.COMMUNITY_EVENT

    # Not usable as a slug: they are paths beside an event's page
    RESERVED_SLUGS = ("new",)

    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, related_name="events", verbose_name=_("Community"),
    )
    kind = models.CharField(_("Kind"), max_length=20, choices=kinds.CHOICES, default=kinds.PROJECT)
    # Set from the title once, unique within the community: its address stays when the
    # title changes
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
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Bumped whenever the event or its needs change, or the ambassador confirms it is
    # still current. Not auto_now: archiving must not make an event look fresh.
    updated_at = models.DateTimeField(_("Updated"), default=timezone.now)
    stale_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(_("Archived"), null=True, blank=True)
    matches = GenericRelation("matches.Match")

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        constraints = [
            models.UniqueConstraint(fields=["community", "slug"], name="one_event_slug_per_community"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._free_slug()
        super().save(*args, **kwargs)

    def _free_slug(self):
        base = slugify(self.title)[:240] or "event"
        taken = set(Event.objects.filter(community_id=self.community_id).values_list("slug", flat=True))
        taken.update(self.RESERVED_SLUGS)
        slug, suffix = base, 1
        while slug in taken:
            suffix += 1
            slug = f"{base}-{suffix}"
        return slug

    def url(self, name="detail", *args):
        """The address of one of its pages: they live under its host's."""
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
    def texts(self):
        """The sentences that name its kind ("This project has ended.")."""
        return kinds.TEXTS[self.kind]

    # ── When ────────────────────────────────────────────────────────
    @property
    def is_ongoing(self):
        return self.ends_on is None

    @property
    def is_over(self):
        return self.ends_on is not None and self.ends_on < timezone.localdate()

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

    # ── Who answers for it, where it is, who may edit ───────────────
    @property
    def manager(self):
        """Who answers for it: matches are addressed to them."""
        return self.community.owner

    @property
    def place(self):
        """Where it happens: something with a name, a rough place for everyone and an
        exact one for those who may know (rough_place, place_for)."""
        return self.community

    def can_edit(self, user):
        return user.is_authenticated and (user.is_staff or user == self.manager)

    def takes_people(self, user=None):
        """Whether someone (or `user`) can offer help or say they come: it is current,
        somebody answers for it, and it is not their own."""
        return self.is_current and self.manager is not None and user != self.manager

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

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.manager

    def get_match_display_name(self):
        return self.title

    def get_match_location(self):
        place = self.place
        return place.name, place.location_name, place.location

    # Where it is, and who may know: its place's
    @property
    def place_seed(self):
        return self.place.place_seed

    @property
    def place_is_public(self):
        return self.place.place_is_public

    def get_match_icon(self):
        return self.kind_icon

    def get_match_kind(self):
        """What a match about it shows as its pill: (label, icon, colour)."""
        return self.kind_label, self.kind_icon, "bg-green"

    def get_match_verb(self):
        return _("offered to help with")

    def get_match_request_text(self):
        return self.texts["help_request"]
