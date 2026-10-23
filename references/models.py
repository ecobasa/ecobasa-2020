from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

# What a reference can be about, as "app_label.model". Kept as strings so this app never
# imports gifts/skills/communities models — same one-directional coupling as matches.
REFERENCEABLE_MODELS = {
    "users.user",
    "communities.community",
    "gifts.listing",
    "skills.userskill",
    "skills.communityskill",
}


def is_referenceable(content_type):
    return f"{content_type.app_label}.{content_type.model}" in REFERENCEABLE_MODELS


def subject_owner(subject):
    """The person a reference about `subject` is ultimately about: the user themself, or
    whoever owns the listing/skill/community (via the matches target protocol)."""
    if isinstance(subject, get_user_model()):
        return subject
    return subject.get_match_owner()


class Reference(models.Model):
    """Someone's experience with a person, community, gift or skill. Free to write —
    it doesn't require a Match, since much of what happens never goes through the platform."""

    TONE_POSITIVE = "positive"
    TONE_NEUTRAL = "neutral"
    TONE_NEGATIVE = "negative"
    TONE_CHOICES = [
        (TONE_POSITIVE, _("Positive")),
        (TONE_NEUTRAL, _("Neutral")),
        (TONE_NEGATIVE, _("Negative")),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="references_given"
    )
    # Denormalized at creation time, like Match.recipient: lets "references about me" be one
    # query across all subject types.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="references_received",
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # CharField: gifts.Listing has a random string primary key.
    object_id = models.CharField(max_length=255)
    subject = GenericForeignKey("content_type", "object_id")

    tone = models.CharField(_("Impression"), max_length=20, choices=TONE_CHOICES, default=TONE_POSITIVE)
    text = models.TextField(_("Your experience"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Reference")
        verbose_name_plural = _("References")
        constraints = [
            models.UniqueConstraint(
                fields=["author", "content_type", "object_id"],
                name="one_reference_per_author_and_subject",
            ),
        ]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return f"Reference from {self.author} → {self.subject} ({self.tone})"
