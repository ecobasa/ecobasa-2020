import secrets
from collections import defaultdict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

# What a reference can be about, as "app_label.model". Kept as strings so this app never
# imports gifts/communities models; subjects are reached through small protocol methods
# (get_match_owner, get_reference_subjects, has_skill/add_skill, get_skill_holder).
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


def references_about(subject):
    """References about `subject` and everything it holds. A user or community lists the
    subjects that belong to it via get_reference_subjects() (themself plus their listings
    and skills), so its page shows all references about it in one place."""
    if hasattr(subject, "get_reference_subjects"):
        subjects = subject.get_reference_subjects()
    else:
        subjects = [subject]
    ids_by_type = defaultdict(list)
    for s in subjects:
        ids_by_type[ContentType.objects.get_for_model(s)].append(str(s.pk))
    query = Q()
    for content_type, ids in ids_by_type.items():
        query |= Q(content_type=content_type, object_id__in=ids)
    # A skill page also lists references about its holder that are tagged with that skill
    if hasattr(subject, "get_skill_holder"):
        holder = subject.get_skill_holder()
        query |= Q(
            content_type=ContentType.objects.get_for_model(holder), object_id=str(holder.pk),
            skill_tags__skill=subject.skill, skill_tags__status=ReferenceSkill.STATUS_CONFIRMED,
        )
    return Reference.objects.filter(query).distinct()


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
    # Skills and gifts the experience was about, only on references about a person or
    # community. Gifts are names only: no listing, image or description is kept.
    skills = models.ManyToManyField(
        "skills.Skill", through="ReferenceSkill", related_name="+", blank=True
    )
    gift_names = models.JSONField(_("Gifts"), default=list, blank=True)
    # Asked for after a match (ReferenceRequest), maybe with a photo. Only references the
    # author agreed to share can be featured on the homepage by staff.
    match = models.ForeignKey(
        "matches.Match", on_delete=models.SET_NULL, null=True, blank=True, related_name="references",
    )
    photo = models.ImageField(_("Photo"), upload_to="reference-photos", null=True, blank=True)
    share_publicly = models.BooleanField(_("ecobasa may show this story on its homepage"), default=False)
    featured_at = models.DateTimeField(_("Featured"), null=True, blank=True)
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


class ReferenceSkill(models.Model):
    """A skill tagged on a reference. If the person or community doesn't have the skill yet,
    it waits for them to confirm it; confirming adds it to their profile."""

    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Waiting for confirmation")),
        (STATUS_CONFIRMED, _("Confirmed")),
        (STATUS_DECLINED, _("Declined")),
    ]

    reference = models.ForeignKey(Reference, on_delete=models.CASCADE, related_name="skill_tags")
    skill = models.ForeignKey("skills.Skill", on_delete=models.CASCADE, related_name="+")
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    class Meta:
        ordering = ["skill__name"]
        verbose_name = _("Reference Skill")
        verbose_name_plural = _("Reference Skills")
        constraints = [
            models.UniqueConstraint(fields=["reference", "skill"], name="one_tag_per_reference_and_skill"),
        ]

    def __str__(self):
        return f"{self.skill} on {self.reference} ({self.status})"

    def confirm(self):
        self.reference.subject.add_skill(self.skill)
        self.status = self.STATUS_CONFIRMED
        self.save(update_fields=["status"])

    def decline(self):
        self.status = self.STATUS_DECLINED
        self.save(update_fields=["status"])


def match_reference_subject(match, user):
    """What `user` writes about after `match`, as (subject, gift name, skill name): the
    requester writes about the community, the skill's holder (tagged with the skill) or
    the owner; the owner writes about the requester. A gift's name is carried along, and
    a skill that was learned or helped with is tagged.
    None if the other side is gone."""
    target = match.target
    if target is None:
        return None
    model = match.content_type.model
    is_requester = user == match.from_user
    if model == "community" and is_requester:
        return target, "", ""
    if hasattr(target, "get_skill_holder") and is_requester:
        return target.get_skill_holder(), "", target.get_match_display_name()
    if model == "skillwish":
        # Someone helped with a wished-for skill: they write about the community that
        # wished for it (or the person); who was helped tags the skill on the helper.
        other = (target.community or match.recipient) if is_requester else match.from_user
        if other is None:
            return None
        return other, "", "" if is_requester else target.get_match_display_name()
    other = match.recipient if is_requester else match.from_user
    if other is None:
        return None
    return other, target.get_match_display_name() if model == "listing" else "", ""


def _request_key():
    # Lowercase hex: it travels in an email address (stories+<key>@…), which some mail
    # servers lowercase.
    return secrets.token_hex(12)


class ReferenceRequest(models.Model):
    """The email asking one side of a match for a reference (their story, as the email
    puts it). Its key is the reply's
    address and the form link, so answering needs no login."""

    match = models.ForeignKey("matches.Match", on_delete=models.CASCADE, related_name="reference_requests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reference_requests")
    key = models.CharField(max_length=32, unique=True, default=_request_key, editable=False)
    reference = models.ForeignKey(
        Reference, on_delete=models.SET_NULL, null=True, blank=True, related_name="reference_requests",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = _("Reference Request")
        verbose_name_plural = _("Reference Requests")
        constraints = [
            models.UniqueConstraint(fields=["match", "user"], name="one_reference_request_per_match_and_user"),
        ]

    def __str__(self):
        return f"Reference request to {self.user} about {self.match}"
