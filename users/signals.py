from datetime import timedelta

from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone


@receiver(user_logged_in)
def remember_language(sender, request, user, **kwargs):
    """Users who never touched the language switcher get the language they're
    browsing in, so emails to them aren't sent in the site default."""
    from django.utils.translation import get_language
    if not user.language and request is not None:
        user.language = get_language() or ""
        user.save(update_fields=["language"])


# How long a read reminder stays quiet before it is shown again
SKILL_NUDGE_INTERVAL = timedelta(days=7)


@receiver(user_logged_in)
def create_skill_nudge_notification(sender, request, user, **kwargs):
    """Remind people without skills to add some. There is at most one reminder per
    person: once read, it shows up again (unread, on top) after a week at the earliest,
    instead of a new one being added on every login."""
    from gifts.models import Listing
    has_skills = Listing.objects.of(user).filter(kind=Listing.KIND_SKILL).exists()
    if has_skills:
        return
    from notifications.models import Notification, SKILL_NUDGE_TEXT
    nudge = Notification.objects.filter(recipient=user, tag=Notification.TAG_SKILL_NUDGE).first()
    if nudge is None:
        Notification.objects.create(
            recipient=user,
            verb=str(SKILL_NUDGE_TEXT),
            link=reverse("gifts:create") + "?type=offer&kind=skill",
            tag=Notification.TAG_SKILL_NUDGE,
        )
    elif nudge.is_read and nudge.created_at < timezone.now() - SKILL_NUDGE_INTERVAL:
        Notification.objects.filter(pk=nudge.pk).update(is_read=False, created_at=timezone.now())


@receiver(post_save, sender="gifts.Listing")
def remove_skill_nudge_on_skill_added(sender, instance, created, **kwargs):
    """Once someone has a skill (or wants to learn one), the reminder is no longer true:
    remove it."""
    if not created or not instance.owner_id or instance.kind != instance.KIND_SKILL:
        return
    from notifications.models import Notification
    Notification.objects.filter(recipient_id=instance.owner_id, tag=Notification.TAG_SKILL_NUDGE).delete()
