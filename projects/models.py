from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from communities.models import Community
from gifts import units


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
    """One thing a project needs: people with a skill, a material, a tool or knowledge,
    with how much of it ("2 people", "200 kg"), so offers can cover it in parts."""

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
        KIND_SKILL: "fa-graduation-cap",
        KIND_MATERIAL: "fa-cubes",
        KIND_TOOL: "fa-screwdriver-wrench",
        KIND_KNOWLEDGE: "fa-lightbulb",
    }
    # Things that can be given, like gifts: they can have a gift category, so they show
    # up with gifts of that category on the map and next to matching gift offers.
    THING_KINDS = (KIND_MATERIAL, KIND_TOOL)
    # Pill colour by kind, like skills (purple) and gifts (primary) elsewhere
    KIND_COLOURS = {KIND_SKILL: "bg-purple", KIND_KNOWLEDGE: "bg-purple", KIND_MATERIAL: "bg-primary", KIND_TOOL: "bg-primary"}

    UNIT_PEOPLE = units.PEOPLE
    UNIT_CHOICES = units.UNIT_CHOICES

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
    category = models.ForeignKey(
        "gifts.ListingCategory", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="project_needs", verbose_name=_("Gift category"),
    )
    quantity = models.PositiveIntegerField(_("How many / how much?"), null=True, blank=True)
    unit = models.CharField(_("Unit"), max_length=10, choices=UNIT_CHOICES, blank=True)
    details = models.CharField(_("Details"), max_length=100, blank=True)
    # The help offers (matches) that include this need, with how much each brings
    offers = models.ManyToManyField("matches.Match", through="NeedOffer", related_name="needs", blank=True)
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
    def colour(self):
        return self.KIND_COLOURS.get(self.kind, "bg-primary")

    @property
    def display_title(self):
        return self.skill.get_name() if self.skill_id else self.title

    def format_amount(self, quantity):
        """"1 person", "3 people", "200 kg"."""
        return units.format_amount(quantity, self.unit)

    @property
    def amount(self):
        """How much is needed, in words: "200 kg, about 15 cm thick"."""
        return ", ".join(part for part in (self.format_amount(self.quantity), self.details) if part)

    def _offers_by_status(self):
        """(accepted, waiting) NeedOffers, each with its match."""
        from matches.models import Match
        offers = list(self.need_offers.all())
        accepted = [o for o in offers if o.match.status == Match.STATUS_ACCEPTED]
        waiting = [o for o in offers if o.match.status in (Match.STATUS_PENDING, Match.STATUS_COUNTER)]
        return accepted, waiting

    @staticmethod
    def _sum(offers):
        return sum(o.quantity for o in offers if o.quantity)

    @property
    def promised_quantity(self):
        return self._sum(self._offers_by_status()[0])

    @property
    def offered_quantity(self):
        return self._sum(self._offers_by_status()[1])

    @property
    def remaining(self):
        """How much is still missing, if the need has a quantity."""
        if self.quantity is None:
            return None
        return max(self.quantity - self.promised_quantity, 0)

    @property
    def status(self):
        """covered (marked by the ambassador) > promised (accepted offers cover it) >
        offered (an offer waits for an answer, or accepted ones cover only part) > open.

        With a quantity, accepted offers cover it once they add up to it; an accepted offer
        that doesn't say how much covers it on its own."""
        if self.covered_at:
            return self.STATUS_COVERED
        accepted, waiting = self._offers_by_status()
        if accepted and (
            self.quantity is None
            or any(o.quantity is None for o in accepted)
            or self._sum(accepted) >= self.quantity
        ):
            return self.STATUS_PROMISED
        if waiting or accepted:
            return self.STATUS_OFFERED
        return self.STATUS_OPEN

    @property
    def is_done(self):
        return self.status in (self.STATUS_COVERED, self.STATUS_PROMISED)

    @property
    def progress(self):
        """"120 of 200 kg promised" while accepted offers cover part of a quantity."""
        if self.quantity is None or self.is_done:
            return ""
        promised = self.promised_quantity
        if not promised:
            return ""
        return _("%(promised)s of %(amount)s promised") % {
            "promised": promised, "amount": self.format_amount(self.quantity),
        }

    @property
    def promises(self):
        """The accepted offers for this need, each with the helper (match.from_user) and
        how much they bring (amount)."""
        return self._offers_by_status()[0]

    def promised_by(self):
        return [o.match.from_user for o in self._offers_by_status()[0]]


class NeedOffer(models.Model):
    """A help offer (match) for one need, with how much of it the helper brings."""

    need = models.ForeignKey(Need, on_delete=models.CASCADE, related_name="need_offers")
    match = models.ForeignKey("matches.Match", on_delete=models.CASCADE, related_name="need_offers")
    quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "projects_need_offers"
        unique_together = [("need", "match")]

    def __str__(self):
        return f"{self.match} → {self.need}"

    @property
    def amount(self):
        return self.need.format_amount(self.quantity)

