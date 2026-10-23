from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
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

# Subjects a person holds themselves. References about these are also listed on the
# owner's profile; community skills belong to the community, not its owner.
PERSONAL_MODELS = {"users.user", "gifts.listing", "skills.userskill"}


def _label(content_type):
    return f"{content_type.app_label}.{content_type.model}"


def is_referenceable(content_type):
    return _label(content_type) in REFERENCEABLE_MODELS


def subject_owner(subject):
    """The person a reference about `subject` is ultimately about: the user themself, or
    whoever owns the listing/skill/community (via the matches target protocol)."""
    if isinstance(subject, get_user_model()):
        return subject
    return subject.get_match_owner()


def references_about(subject):
    """References about `subject`. For a user, this includes the references about their
    gift listings and skills too, so their profile shows everything about them in one place."""
    if isinstance(subject, get_user_model()):
        personal = Q()
        for label in PERSONAL_MODELS:
            app_label, model = label.split(".")
            personal |= Q(content_type__app_label=app_label, content_type__model=model)
        return Reference.objects.filter(personal, recipient=subject)
    content_type = ContentType.objects.get_for_model(subject)
    return Reference.objects.filter(content_type=content_type, object_id=str(subject.pk))


class Reference(models.Model):
    """Someone's experience with a person, community, gift or skill. Free to write —
    it doesn't require a Match, since much of what happens never goes through the platform."""

    IMPRESSION_POSITIVE = "positive"
    IMPRESSION_NEUTRAL = "neutral"
    IMPRESSION_NEGATIVE = "negative"
    IMPRESSION_CHOICES = [
        (IMPRESSION_POSITIVE, _("Positive")),
        (IMPRESSION_NEUTRAL, _("Neutral")),
        (IMPRESSION_NEGATIVE, _("Negative")),
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

    impression = models.CharField(_("Impression"), max_length=20, choices=IMPRESSION_CHOICES, default=IMPRESSION_POSITIVE)
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
        return f"Reference from {self.author} → {self.subject} ({self.impression})"
