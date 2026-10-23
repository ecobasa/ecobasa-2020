from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import get_language, gettext_lazy as _

from users.models import User
from communities.models import Community


def _user_slug(user):
    """Mirrors User.get_absolute_url() slug logic — always returns a non-empty string."""
    return user.username or slugify(user.name) or str(user.pk)


class SkillTaxonomy(models.Model):
    names = models.JSONField(default=dict)
    slug        = models.SlugField(max_length=120, unique=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug"]
        verbose_name = _("Skill taxonomy")
        verbose_name_plural = _("Skill taxonomy")

    def get_name(self, lang="en"):
        return self.names.get(lang) or self.names.get("en") or next(iter(self.names.values()), "")

    def __str__(self):
        return self.get_name()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.get_name())[:100]
            slug, n = base, 1
            while SkillTaxonomy.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)
        _clear_taxonomy_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        _clear_taxonomy_cache()


# ── Taxonomy lookups ────────────────────────────────────────────────
# A Skill is linked to its SkillTaxonomy entry by sharing the same slug. The
# taxonomy holds the per-language names, so a Skill is stored once (English
# name) and displayed in the visitor's language.

_taxonomy_cache = None


def _clear_taxonomy_cache():
    global _taxonomy_cache
    _taxonomy_cache = None


def _taxonomy():
    """({slug: names}, {lowercased name in any language: slug}), cached per process."""
    global _taxonomy_cache
    if _taxonomy_cache is None:
        by_slug = dict(SkillTaxonomy.objects.values_list("slug", "names"))
        by_name = {}
        for slug, names in by_slug.items():
            for name in names.values():
                by_name.setdefault(name.strip().lower(), slug)
        _taxonomy_cache = (by_slug, by_name)
    return _taxonomy_cache


def skill_slugs_matching(q):
    """Taxonomy slugs whose name in any language contains q (case-insensitive)."""
    q = q.strip().lower()
    if not q:
        return []
    return [slug for slug, names in _taxonomy()[0].items()
            if any(q in name.lower() for name in names.values())]


def skill_name_q(q, prefix="skill__"):
    """Q matching skills whose name in any language contains q, e.g. "Zimmer" finds Carpentry."""
    return models.Q(**{f"{prefix}name__icontains": q}) | models.Q(**{f"{prefix}slug__in": skill_slugs_matching(q)})


def skill_slug_for_name(name):
    """Slug a skill name (in any language) resolves to, without creating anything."""
    return _taxonomy()[1].get(name.strip().lower()) or slugify(name)


def get_or_create_skill(name=None, slug=None):
    """Resolve a skill name in any language (or a taxonomy slug) to one Skill.

    "Zimmerei", "Menuiserie" and "Carpentry" all resolve to the same Skill.
    Names that are not in the taxonomy fall back to a plain name lookup.
    """
    by_slug, by_name = _taxonomy()
    if slug is None and name:
        slug = by_name.get(name.strip().lower())
    if slug in by_slug:
        skill = Skill.objects.filter(slug=slug).first()
        if skill:
            return skill, False
        en_name = by_slug[slug].get("en") or name
        skill = Skill.objects.filter(name__iexact=en_name).first()
        if skill:
            return skill, False
        return Skill.objects.create(name=en_name, slug=slug), True
    return Skill.objects.get_or_create(name__iexact=name.strip(), defaults={"name": name.strip()})


class Skill(models.Model):
    name = models.CharField(_("Name"), max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Skill")
        verbose_name_plural = _("Skills")

    def __str__(self):
        return self.get_name()

    def get_name(self, lang=None):
        """Name in the given (default: active) language, via the taxonomy entry sharing this slug."""
        names = _taxonomy()[0].get(self.slug)
        if not names:
            return self.name
        lang = (lang or get_language() or "en")[:2]
        return names.get(lang) or names.get("en") or self.name

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
    matches     = GenericRelation("matches.Match")

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

    def get_edit_url(self):
        return reverse("skills:userskill_edit", kwargs={
            "skill_slug": self.skill.slug,
            "user_slug":  _user_slug(self.user),
        })

    def get_delete_url(self):
        return reverse("skills:userskill_delete", kwargs={
            "skill_slug": self.skill.slug,
            "user_slug":  _user_slug(self.user),
        })

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.user

    def get_match_display_name(self):
        return self.skill.get_name()

    def get_match_location(self):
        user = self.user
        label = f"{user.name or user.email}'s place"
        return label, user.location_name, user.location

    def get_match_icon(self):
        return "fa-hand-point-up"

    def get_match_verb(self):
        return _("expressed interest")


class CommunitySkill(models.Model):
    community   = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="community_skills")
    skill       = models.ForeignKey(Skill,     on_delete=models.CASCADE, related_name="community_skills")
    description = models.TextField(_("What can visitors learn here?"), blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    matches     = GenericRelation("matches.Match")

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

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.community.owner

    def get_match_display_name(self):
        return self.skill.get_name()

    def get_match_location(self):
        community = self.community
        return community.name, community.location_name, community.location

    def get_match_icon(self):
        return "fa-hand-point-up"

    def get_match_verb(self):
        return _("expressed interest")


class SkillWish(models.Model):
    """Someone wants to learn a skill, or a community needs someone with a skill."""

    def get_absolute_url(self):
        if self.user:
            return reverse("skills:skillwish_user_detail", kwargs={
                "user_slug":  _user_slug(self.user),
                "skill_slug": self.skill.slug,
            })
        if self.community:
            return reverse("skills:communityskill_detail", kwargs={
                "skill_slug":     self.skill.slug,
                "community_slug": self.community.slug,
            })
        return reverse("skills:skill_detail", kwargs={"slug": self.skill.slug})

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
    matches     = GenericRelation("matches.Match")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Skill Wish")
        verbose_name_plural = _("Skill Wishes")

    def __str__(self):
        owner = self.user or self.community
        return f"{owner} wants: {self.skill}"

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.user or (self.community.owner if self.community else None)

    def get_match_display_name(self):
        return self.skill.get_name()

    def get_match_location(self):
        if self.user:
            label = f"{self.user.name or self.user.email}'s place"
            return label, self.user.location_name, self.user.location
        if self.community:
            return self.community.name, self.community.location_name, self.community.location
        return "", None, None

    def get_match_icon(self):
        return "fa-hand-holding-heart"

    def get_match_verb(self):
        return _("offered to teach you")
