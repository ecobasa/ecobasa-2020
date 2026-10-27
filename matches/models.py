from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


# Matches whose target is in one of these apps are volunteer stays: at a community, or
# helping with one of its projects.
STAY_APP_LABELS = ("communities", "projects")


class Match(models.Model):
    """A negotiation between two users over something one of them has: a gift, a skill,
    or a stay at a community. `target` is whatever is being negotiated over — a Listing,
    UserSkill, CommunitySkill, SkillWish, or Community — via a generic reference, so this
    app never has to import gifts/skills/communities models to work with it.
    """

    LOC_MY_PLACE = "my_place"
    LOC_YOUR_PLACE = "your_place"
    LOC_CUSTOM = "custom"
    LOC_CHOICES = [
        (LOC_MY_PLACE, _("My place — come visit me")),
        (LOC_YOUR_PLACE, _("Your place — I will visit you")),
        (LOC_CUSTOM, _("Somewhere else")),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_COUNTER = "counter"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_ACCEPTED, _("Accepted")),
        (STATUS_DECLINED, _("Declined")),
        (STATUS_COUNTER, _("Counter-proposed")),
    ]

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches_sent"
    )
    # Denormalized at creation time: who this match was directed at. Needed because a
    # GenericForeignKey can't be filtered/joined generically across heterogeneous target
    # types ("show me matches sent to me" would otherwise require a different lookup path
    # per target model). Mirrors the existing Notification.recipient pattern.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="matches_received",
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # CharField, not PositiveIntegerField: gifts.Listing uses a random string primary key
    # (RandomIdMixin), so object_id has to accommodate non-numeric PKs too.
    object_id = models.CharField(max_length=255)
    target = GenericForeignKey("content_type", "object_id")

    message = models.TextField(_("Message"))
    location_type = models.CharField(
        _("Meeting location"), max_length=20, choices=LOC_CHOICES, default=LOC_YOUR_PLACE
    )
    proposed_location = models.CharField(_("Custom location"), max_length=255, blank=True)
    proposed_lat = models.FloatField(null=True, blank=True)
    proposed_lon = models.FloatField(null=True, blank=True)
    proposed_date = models.DateTimeField(_("Proposed date"), null=True, blank=True)
    status = models.CharField(
        _("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Match")
        verbose_name_plural = _("Matches")

    def __str__(self):
        return f"Match from {self.from_user} → {self.target}"

    def get_absolute_url(self):
        return reverse("matches:detail", args=[self.pk])

    @property
    def is_community_stay(self):
        """A volunteer stay happens at the community itself (also when helping with one
        of its projects), so only its dates are open to a counter-proposal, never the place."""
        return self.content_type.app_label in STAY_APP_LABELS

    def stay_period(self):
        """(from, to) of a stay as currently proposed: the latest counter-proposed period,
        else what the volunteer asked for. (None, None) without dates."""
        counter = (
            self.thread.filter(status_to=self.STATUS_COUNTER)
            .exclude(counter_stay_from=None, counter_stay_to=None)
            .last()
        )
        if counter:
            return counter.counter_stay_from, counter.counter_stay_to
        details = getattr(self, "volunteer_details", None)
        if details:
            return details.stay_from, details.stay_to
        return None, None

    def resolved_location(self):
        """Human-readable meeting location, resolving my/your place from profiles."""
        if self.location_type == self.LOC_MY_PLACE:
            loc = self.from_user.location_name or self.proposed_location or ""
            name = self.from_user.name or self.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        if self.location_type == self.LOC_YOUR_PLACE and self.target is not None:
            label, loc_name, _point = self.target.get_match_location()
            if label:
                return f"{label} — {loc_name}" if loc_name else label
        return self.proposed_location or ""

    def location_coords(self):
        """Best coordinates for this match's proposed meeting point."""
        if self.proposed_lat and self.proposed_lon:
            return self.proposed_lat, self.proposed_lon
        if self.location_type == self.LOC_MY_PLACE and self.from_user.location:
            return self.from_user.location.y, self.from_user.location.x
        if self.location_type == self.LOC_YOUR_PLACE and self.target is not None:
            _label, _loc_name, point = self.target.get_match_location()
            if point:
                return point.y, point.x
        return None, None


class MatchMessage(models.Model):
    """One entry in a Match conversation thread — a plain message or a status decision."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="thread")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(_("Message"), blank=True)
    status_to = models.CharField(
        _("Decision"), max_length=20, blank=True, choices=Match.STATUS_CHOICES
    )
    counter_location_type = models.CharField(max_length=20, blank=True, choices=Match.LOC_CHOICES)
    counter_location = models.CharField(max_length=255, blank=True)
    counter_lat = models.FloatField(null=True, blank=True)
    counter_lon = models.FloatField(null=True, blank=True)
    counter_date = models.DateTimeField(null=True, blank=True)
    # Counter-proposed stay period, for community stays (see VolunteerDetails.stay_from/to)
    counter_stay_from = models.DateTimeField(null=True, blank=True)
    counter_stay_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Match Message")
        verbose_name_plural = _("Match Messages")

    def __str__(self):
        return f"{self.sender} → {self.match} ({self.status_to or 'message'})"

    def resolved_counter_location(self):
        """Human-readable counter-proposed meeting location, resolving my/your place."""
        if self.counter_location:
            return self.counter_location
        match = self.match
        if self.counter_location_type == Match.LOC_MY_PLACE and match.target is not None:
            label, loc_name, _point = match.target.get_match_location()
            if label:
                return f"{label} — {loc_name}" if loc_name else label
        if self.counter_location_type == Match.LOC_YOUR_PLACE:
            loc = match.from_user.location_name or ""
            name = match.from_user.name or match.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        return ""

    def counter_location_coords(self):
        if self.counter_lat and self.counter_lon:
            return self.counter_lat, self.counter_lon
        match = self.match
        if self.counter_location_type == Match.LOC_MY_PLACE and match.target is not None:
            _label, _loc_name, point = match.target.get_match_location()
            if point:
                return point.y, point.x
        if self.counter_location_type == Match.LOC_YOUR_PLACE and match.from_user.location:
            return match.from_user.location.y, match.from_user.location.x
        return None, None


class VolunteerDetails(models.Model):
    """Volunteer-only extra fields that don't generalize to gifts/skills matches."""

    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="volunteer_details")
    volunteer_mode = models.CharField(max_length=20, blank=True)  # 'offer' | 'wish'
    stay_from = models.DateTimeField(null=True, blank=True)
    stay_to = models.DateTimeField(null=True, blank=True)
    practice_skills = models.CharField(max_length=500, blank=True)
    practice_skill_level = models.CharField(max_length=20, blank=True)
    sender_skills = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = _("Volunteer Details")
        verbose_name_plural = _("Volunteer Details")

    def __str__(self):
        return f"Volunteer details for {self.match}"

    @property
    def practice_skills_list(self):
        return [s.strip() for s in self.practice_skills.split(",") if s.strip()] if self.practice_skills else []

    @property
    def sender_skills_list(self):
        return [s.strip() for s in self.sender_skills.split(",") if s.strip()] if self.sender_skills else []

    @property
    def sender_skills_with_levels(self):
        from skills.models import UserSkill, skill_slug_for_name
        names = self.sender_skills_list
        if not names:
            return []
        level_map = {
            us.skill.slug: us.get_level_display()
            for us in UserSkill.objects.filter(user=self.match.from_user).select_related("skill")
            if us.level
        }
        return [(name, level_map.get(skill_slug_for_name(name))) for name in names]


def _name(user):
    return (user.name or user.email) if user else ""


class Suggestion(models.Model):
    """Something of someone else's that fits something of yours, found by the matching
    (matching.py) as soon as either was saved: their gift offer for your wish, their wish
    for your offer, a project that needs your skill, a person with the skill your project
    or your wish asks for. Each pair is suggested to both sides, each within their own
    distance (User.match_radius)."""

    REASON_SKILL = "skill"
    REASON_WORDS = "words"
    REASON_CHOICES = [
        (REASON_SKILL, _("Same skill")),
        (REASON_WORDS, _("Similar title")),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suggestions")
    # Their own thing it fits: a gift listing, skill, skill wish or project need
    own_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    own_id = models.CharField(max_length=255)
    own = GenericForeignKey("own_type", "own_id")
    # Someone else's thing
    other_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    other_id = models.CharField(max_length=255)
    other = GenericForeignKey("other_type", "other_id")
    other_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    KIND_GIFT = "gift"
    KIND_SKILLS = "skills"
    # Things (gifts, and materials and tools for projects) or skills (and knowledge)
    KIND_CHOICES = [(KIND_GIFT, _("Gifts")), (KIND_SKILLS, _("Skills"))]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_GIFT)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    distance_km = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "own_type", "own_id", "other_type", "other_id"], name="one_suggestion_per_pair",
            ),
        ]
        indexes = [models.Index(fields=["other_type", "other_id"]), models.Index(fields=["own_type", "own_id"])]
        verbose_name = _("Suggestion")
        verbose_name_plural = _("Suggestions")

    def __str__(self):
        return f"{self.user} ← {self.other}"

    @property
    def other_model(self):
        return self.other_type.model

    @property
    def icon(self):
        return {
            "listing": "fa-gift" if getattr(self.other, "type", "") == "offer" else "fa-heart",
            "need": "fa-person-digging",
            "userskill": "fa-graduation-cap",
            "communityskill": "fa-graduation-cap",
            "skillwish": "fa-magnifying-glass",
        }.get(self.other_model, "fa-handshake-angle")

    @property
    def text(self):
        """What the other side has or needs, in the reader's language."""
        other, model = self.other, self.other_model
        if other is None:
            return ""
        if model == "listing":
            title = f"{other.title} ({other.amount})" if other.amount else other.title
            template = _("%(name)s gives away: %(title)s") if other.type == "offer" else _("%(name)s is looking for: %(title)s")
            return template % {"name": _name(other.owner), "title": title}
        if model == "need":
            title = f"{other.display_title} ({other.amount})" if other.amount else other.display_title
            return _("%(project)s at %(community)s needs: %(title)s") % {
                "project": other.project.title, "community": other.project.community.name, "title": title,
            }
        if model == "userskill":
            return _("%(name)s offers the skill: %(skill)s") % {"name": _name(other.user), "skill": other.skill.get_name()}
        if model == "communityskill":
            return _("You can learn %(skill)s at %(community)s") % {
                "skill": other.skill.get_name(), "community": other.community.name,
            }
        if model == "skillwish":
            if other.community_id:
                return _("%(community)s is looking for: %(skill)s") % {
                    "community": other.community.name, "skill": other.skill.get_name(),
                }
            return _("%(name)s wants to learn: %(skill)s") % {"name": _name(other.user), "skill": other.skill.get_name()}
        return str(other)

    @property
    def own_text(self):
        """Which of their own things it fits."""
        own, model = self.own, self.own_type.model
        if own is None:
            return ""
        if model == "listing":
            template = _("your offer: %(title)s") if own.type == "offer" else _("your wish: %(title)s")
            return template % {"title": own.title}
        if model == "need":
            return _("your project %(project)s: %(title)s") % {"project": own.project.title, "title": own.display_title}
        if model in ("userskill", "communityskill"):
            return _("your skill: %(skill)s") % {"skill": own.skill.get_name()}
        if model == "skillwish":
            return _("your wish: %(title)s") % {"title": own.skill.get_name()}
        return str(own)

    @property
    def url(self):
        """Where to act on it: the offer form for a project need, else the thing's page
        (where a gift or a skill can be asked for)."""
        other = self.other
        if other is None:
            return ""
        if self.other_model == "need":
            return f"{reverse('projects:offer_help', args=[other.project_id])}?need={other.pk}"
        return other.get_absolute_url()
