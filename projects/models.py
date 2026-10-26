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

    def open_needs(self):
        return [need for need in self.needs.all() if need.status == Need.STATUS_OPEN]

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


class Need(models.Model):
    """One thing a project needs: people with a skill, a material, a tool or knowledge."""

    KIND_SKILL = "skill"
    KIND_MATERIAL = "material"
    KIND_TOOL = "tool"
    KIND_KNOWLEDGE = "knowledge"
    KIND_CHOICES = [
        (KIND_SKILL, _("Helping hands / skill")),
        (KIND_MATERIAL, _("Material")),
        (KIND_TOOL, _("Tool")),
        (KIND_KNOWLEDGE, _("Knowledge")),
    ]
    KIND_ICONS = {
        KIND_SKILL: "fa-hands-helping",
        KIND_MATERIAL: "fa-cubes",
        KIND_TOOL: "fa-screwdriver-wrench",
        KIND_KNOWLEDGE: "fa-lightbulb",
    }

    STATUS_OPEN = "open"
    STATUS_OFFERED = "offered"
    STATUS_PROMISED = "promised"
    STATUS_COVERED = "covered"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="needs")
    kind = models.CharField(_("Kind"), max_length=20, choices=KIND_CHOICES, default=KIND_SKILL)
    title = models.CharField(_("What is needed?"), max_length=255)
    # Set when the title is a known skill (in any language), so people with that skill
    # can be found for it.
    skill = models.ForeignKey(
        "skills.Skill", on_delete=models.SET_NULL, null=True, blank=True, related_name="project_needs",
    )
    amount = models.CharField(_("How much / how many?"), max_length=100, blank=True)
    # The help offers (matches) that include this need
    offers = models.ManyToManyField("matches.Match", related_name="needs", blank=True)
    # Marked as covered by the ambassador, however it was covered
    covered_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("Need")
        verbose_name_plural = _("Needs")

    def __str__(self):
        return self.title

    @property
    def icon(self):
        return self.KIND_ICONS.get(self.kind, "fa-circle")

    @property
    def display_title(self):
        return self.skill.get_name() if self.skill_id else self.title

    def _offers_by_status(self):
        from matches.models import Match
        offers = list(self.offers.all())
        accepted = [m for m in offers if m.status == Match.STATUS_ACCEPTED]
        waiting = [m for m in offers if m.status in (Match.STATUS_PENDING, Match.STATUS_COUNTER)]
        return accepted, waiting

    @property
    def status(self):
        """covered (marked by the ambassador) > promised (an accepted offer) > offered
        (an offer waiting for an answer) > open."""
        if self.covered_at:
            return self.STATUS_COVERED
        accepted, waiting = self._offers_by_status()
        if accepted:
            return self.STATUS_PROMISED
        if waiting:
            return self.STATUS_OFFERED
        return self.STATUS_OPEN

    @property
    def is_done(self):
        return self.status in (self.STATUS_COVERED, self.STATUS_PROMISED)

    def promised_by(self):
        return [m.from_user for m in self._offers_by_status()[0]]
