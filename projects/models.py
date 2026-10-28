from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from communities.models import Community


class ProjectQuerySet(models.QuerySet):
    def current(self):
        """Not archived and not over yet. Projects without an end date are ongoing."""
        today = timezone.localdate()
        return self.filter(archived_at=None).filter(models.Q(ends_on=None) | models.Q(ends_on__gte=today))


class Project(models.Model):
    """Something a community wants to realise with help from outside, e.g. "Build a rocket
    stove, March–April": what it needs (volunteers with skills, materials, tools,
    knowledge) and what the community provides in return. Dated projects end with their
    end date; ongoing ones have none and stay current as long as someone keeps them up to
    date (see freshness.py).

    Hosted by a community for now. Community tours (a route with stops) are meant to
    become another kind of event later, with the same needs, matches and calendar.
    """

    community = models.ForeignKey(
        Community, on_delete=models.CASCADE, related_name="projects", verbose_name=_("Community"),
    )
    title = models.CharField(_("Title"), max_length=255)
    description = models.TextField(_("Description"), blank=True)
    starts_on = models.DateField(_("From"), null=True, blank=True)
    ends_on = models.DateField(
        _("Until"), null=True, blank=True,
        help_text=_("Leave empty for an ongoing project without an end date."),
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
    # Bumped whenever the project or its needs change, or the ambassador confirms it is
    # still current. Not auto_now: archiving must not make a project look fresh.
    updated_at = models.DateTimeField(_("Updated"), default=timezone.now)
    stale_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(_("Archived"), null=True, blank=True)
    matches = GenericRelation("matches.Match")

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("projects:detail", kwargs={"pk": self.pk})

    @property
    def is_ongoing(self):
        return self.ends_on is None

    @property
    def is_over(self):
        return self.ends_on is not None and self.ends_on < timezone.localdate()

    @property
    def is_current(self):
        return self.archived_at is None and not self.is_over

    def touch(self, save=True):
        """Mark the project as up to date (an edit or a confirmation)."""
        self.updated_at = timezone.now()
        self.stale_reminder_sent_at = None
        if self.archived_at and not self.is_over:
            self.archived_at = None
        if save:
            self.save(update_fields=["updated_at", "stale_reminder_sent_at", "archived_at"])

    def stale_since(self):
        return self.updated_at + timedelta(days=settings.PROJECT_STALE_DAYS)

    def can_edit(self, user):
        return user.is_authenticated and (user.is_staff or user == self.community.owner)

    # Its needs are the community's wishes in it, and what you can learn here its skill
    # offers in it (gifts.Listing.project). Both are listed only while it runs.
    def needs(self):
        return sorted((l for l in self.listings.all() if l.is_wish), key=lambda l: (l.order, l.created_at))

    def skills_to_learn(self):
        return sorted((l for l in self.listings.all() if l.is_offer and l.skill_id), key=lambda l: l.display_title)

    def open_needs(self):
        return [need for need in self.needs() if need.status == need.STATUS_OPEN]

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.community.owner

    def get_match_display_name(self):
        return self.title

    def get_match_location(self):
        community = self.community
        return community.name, community.location_name, community.location

    def get_match_icon(self):
        return "fa-person-digging"

    def get_match_verb(self):
        return _("offered to help with")

    def get_match_request_text(self):
        return _("%(actor)s offered to help with your project: %(title)s")
