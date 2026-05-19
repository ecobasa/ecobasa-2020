from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from users.models import User
from communities.models import Community


def _user_slug(user):
    """Mirrors User.get_absolute_url() slug logic — always returns a non-empty string."""
    return user.username or slugify(user.name) or str(user.pk)


class Skill(models.Model):
    name = models.CharField(_("Name"), max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Skill")
        verbose_name_plural = _("Skills")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("skills:skill_detail", kwargs={"slug": self.slug})


class UserSkill(models.Model):
    LEVEL_BEGINNER     = "beginner"
    LEVEL_INTERMEDIATE = "intermediate"
    LEVEL_ADVANCED     = "advanced"
    LEVEL_EXPERT       = "expert"
    LEVEL_CHOICES = [
        (LEVEL_BEGINNER,     _("Beginner")),
        (LEVEL_INTERMEDIATE, _("Intermediate")),
        (LEVEL_ADVANCED,     _("Advanced")),
        (LEVEL_EXPERT,       _("Expert")),
    ]

    user        = models.ForeignKey(User,  on_delete=models.CASCADE, related_name="user_skills")
    skill       = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="user_skills")
    level       = models.CharField(_("Level"), max_length=20, choices=LEVEL_CHOICES, blank=True)
    description = models.TextField(
        _("How did you learn this? What can you offer?"), blank=True
    )
    available   = models.BooleanField(
        _("Available to teach / share"), default=True
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "skill")
        ordering = ["skill__name"]
        verbose_name = _("User Skill")
        verbose_name_plural = _("User Skills")

    def __str__(self):
        return f"{self.user} — {self.skill}"

    def get_absolute_url(self):
        return reverse("skills:userskill_detail", kwargs={
            "skill_slug": self.skill.slug,
            "user_slug":  _user_slug(self.user),
        })


class CommunitySkill(models.Model):
    community   = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="community_skills")
    skill       = models.ForeignKey(Skill,     on_delete=models.CASCADE, related_name="community_skills")
    description = models.TextField(_("What can visitors learn here?"), blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("community", "skill")
        ordering = ["skill__name"]
        verbose_name = _("Community Skill")
        verbose_name_plural = _("Community Skills")

    def __str__(self):
        return f"{self.community} — {self.skill}"

    def get_absolute_url(self):
        return reverse("skills:communityskill_detail", kwargs={
            "skill_slug":     self.skill.slug,
            "community_slug": self.community.slug,
        })


class SkillRequest(models.Model):
    LOC_MY_PLACE   = "my_place"
    LOC_YOUR_PLACE = "your_place"
    LOC_CUSTOM     = "custom"
    LOC_CHOICES = [
        (LOC_MY_PLACE,   _("My place — come visit me")),
        (LOC_YOUR_PLACE, _("Your place — I will visit you")),
        (LOC_CUSTOM,     _("Somewhere else")),
    ]

    STATUS_PENDING  = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_COUNTER  = "counter"
    STATUS_CHOICES = [
        (STATUS_PENDING,  _("Pending")),
        (STATUS_ACCEPTED, _("Accepted")),
        (STATUS_DECLINED, _("Declined")),
        (STATUS_COUNTER,  _("Counter-proposed")),
    ]

    from_user         = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="skill_requests_sent"
    )
    user_skill        = models.ForeignKey(
        UserSkill, null=True, blank=True,
        on_delete=models.CASCADE, related_name="requests"
    )
    community_skill   = models.ForeignKey(
        CommunitySkill, null=True, blank=True,
        on_delete=models.CASCADE, related_name="requests"
    )
    message           = models.TextField(_("Message"))
    location_type     = models.CharField(
        _("Meeting location"), max_length=20, choices=LOC_CHOICES, default=LOC_YOUR_PLACE
    )
    proposed_location = models.CharField(_("Custom location"), max_length=255, blank=True)
    proposed_lat      = models.FloatField(null=True, blank=True)
    proposed_lon      = models.FloatField(null=True, blank=True)
    proposed_date     = models.DateTimeField(_("Proposed date"), null=True, blank=True)
    status            = models.CharField(
        _("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    response_message  = models.TextField(_("Response message"), blank=True)
    counter_location_type = models.CharField(
        _("Counter location"), max_length=20, choices=LOC_CHOICES, blank=True
    )
    counter_location  = models.CharField(max_length=255, blank=True)
    counter_lat       = models.FloatField(null=True, blank=True)
    counter_lon       = models.FloatField(null=True, blank=True)
    counter_date      = models.DateTimeField(_("Counter date"), null=True, blank=True)
    responded_at      = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        return reverse("matches:skillrequest_detail", kwargs={"pk": self.pk})

    def resolved_location(self):
        """Human-readable meeting location, resolving my/your place from profiles."""
        if self.location_type == self.LOC_MY_PLACE:
            loc = self.from_user.location_name or self.proposed_location or ""
            name = self.from_user.name or self.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        if self.location_type == self.LOC_YOUR_PLACE:
            target_user = self.user_skill.user if self.user_skill else None
            if target_user:
                loc = target_user.location_name or ""
                name = target_user.name or target_user.email
                return f"{name}'s place — {loc}" if loc else f"{name}'s place"
            if self.community_skill:
                loc = self.community_skill.community.location_name or ""
                return f"{self.community_skill.community.name} — {loc}" if loc else self.community_skill.community.name
        return self.proposed_location or ""

    def location_coords(self):
        """Best coordinates for this request's proposed meeting point."""
        if self.proposed_lat and self.proposed_lon:
            return self.proposed_lat, self.proposed_lon
        if self.location_type == self.LOC_MY_PLACE and self.from_user.location:
            return self.from_user.location.y, self.from_user.location.x
        if self.location_type == self.LOC_YOUR_PLACE:
            target = self.user_skill.user if self.user_skill else None
            if target and target.location:
                return target.location.y, target.location.x
            if self.community_skill and self.community_skill.community.location:
                c = self.community_skill.community.location
                return c.y, c.x
        return None, None

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Skill Request")
        verbose_name_plural = _("Skill Requests")

    def __str__(self):
        target = self.user_skill or self.community_skill
        return f"Request from {self.from_user} → {target}"


class SkillRequestMessage(models.Model):
    """One entry in a SkillRequest conversation thread — plain message or a status decision."""
    request      = models.ForeignKey(SkillRequest, on_delete=models.CASCADE, related_name="thread")
    sender       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skill_request_messages")
    body         = models.TextField(_("Message"), blank=True)
    status_to    = models.CharField(
        _("Decision"), max_length=20, blank=True, choices=SkillRequest.STATUS_CHOICES
    )
    counter_location_type = models.CharField(max_length=20, blank=True, choices=SkillRequest.LOC_CHOICES)
    counter_location      = models.CharField(max_length=255, blank=True)
    counter_lat           = models.FloatField(null=True, blank=True)
    counter_lon           = models.FloatField(null=True, blank=True)
    counter_date          = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Skill Request Message")
        verbose_name_plural = _("Skill Request Messages")

    def __str__(self):
        return f"{self.sender} → {self.request} ({self.status_to or 'message'})"

    def resolved_counter_location(self):
        """Human-readable counter-proposed meeting location, resolving my/your place from profiles."""
        if self.counter_location:
            return self.counter_location
        sr = self.request
        if self.counter_location_type == SkillRequest.LOC_MY_PLACE:
            if sr.user_skill:
                owner = sr.user_skill.user
                loc = owner.location_name or ""
                name = owner.name or owner.email
                return f"{name}'s place — {loc}" if loc else f"{name}'s place"
            if sr.community_skill:
                loc = sr.community_skill.community.location_name or ""
                name = sr.community_skill.community.name
                return f"{name} — {loc}" if loc else name
        if self.counter_location_type == SkillRequest.LOC_YOUR_PLACE:
            loc = sr.from_user.location_name or ""
            name = sr.from_user.name or sr.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        return ""

    def counter_location_coords(self):
        if self.counter_lat and self.counter_lon:
            return self.counter_lat, self.counter_lon
        sr = self.request
        if self.counter_location_type == SkillRequest.LOC_MY_PLACE:
            owner = sr.user_skill.user if sr.user_skill else None
            if owner and owner.location:
                return owner.location.y, owner.location.x
        if self.counter_location_type == SkillRequest.LOC_YOUR_PLACE and sr.from_user.location:
            return sr.from_user.location.y, sr.from_user.location.x
        return None, None


class SkillWish(models.Model):
    """Someone wants to learn a skill, or a community needs someone with a skill."""
    user        = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.CASCADE, related_name="skill_wishes"
    )
    community   = models.ForeignKey(
        Community, null=True, blank=True,
        on_delete=models.CASCADE, related_name="skill_wishes"
    )
    skill       = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="wishes")
    # For user wishes: their current level. For community wishes: minimum level sought.
    level       = models.CharField(max_length=20, blank=True,
                                   choices=UserSkill.LEVEL_CHOICES)
    description = models.TextField(
        _("What do you want to learn, or what do you need?"), blank=True
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Skill Wish")
        verbose_name_plural = _("Skill Wishes")

    def __str__(self):
        owner = self.user or self.community
        return f"{owner} wants: {self.skill}"
