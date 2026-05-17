from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from users.models import User
from communities.models import Community


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
            "username": self.user.username,
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
            "skill_slug": self.skill.slug,
            "community_slug": self.community.slug,
        })


class SkillRequest(models.Model):
    from_user        = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="skill_requests_sent"
    )
    user_skill       = models.ForeignKey(
        UserSkill, null=True, blank=True,
        on_delete=models.CASCADE, related_name="requests"
    )
    community_skill  = models.ForeignKey(
        CommunitySkill, null=True, blank=True,
        on_delete=models.CASCADE, related_name="requests"
    )
    message          = models.TextField(_("Message"))
    proposed_location = models.CharField(_("Proposed location"), max_length=255, blank=True)
    proposed_date    = models.DateField(_("Proposed date"), null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Skill Request")
        verbose_name_plural = _("Skill Requests")

    def __str__(self):
        target = self.user_skill or self.community_skill
        return f"Request from {self.from_user} → {target}"
