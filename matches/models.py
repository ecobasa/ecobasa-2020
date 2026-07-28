from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class Match(models.Model):
    """A negotiation between two users over something one of them has: a gift, a skill,
    or a stay at a community. `target` is whatever is being negotiated over — an Ad,
    UserSkill, CommunitySkill, SkillWish, or Community — via a generic reference, so this
    app never has to import gifting/skills/communities models to work with it.
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
    # CharField, not PositiveIntegerField: gifting.Ad uses a random string primary key
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
        from skills.models import UserSkill
        names = self.sender_skills_list
        if not names:
            return []
        level_map = {
            us.skill.name: us.get_level_display()
            for us in UserSkill.objects.filter(
                user=self.match.from_user, skill__name__in=names,
            ).select_related("skill")
            if us.level
        }
        return [(name, level_map.get(name)) for name in names]
