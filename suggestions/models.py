from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _name(user):
    return (user.name or user.email) if user else ""


class Suggestion(models.Model):
    """Something of someone else's that fits something of yours, found by the matching
    (engine.py) as soon as either was saved: their gift offer for your wish, their wish
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
