from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse


@receiver(user_logged_in)
def remember_language(sender, request, user, **kwargs):
    """Users who never touched the language switcher get the language they're
    browsing in, so emails to them aren't sent in the site default."""
    from django.utils.translation import get_language
    if not user.language and request is not None:
        user.language = get_language() or ""
        user.save(update_fields=["language"])


@receiver(user_logged_in)
def create_skill_nudge_notification(sender, request, user, **kwargs):
    has_skills = user.user_skills.exists() or user.skill_wishes.exists()
    if has_skills:
        return
    from notifications.models import Notification, SKILL_NUDGE_TEXT
    already_exists = Notification.objects.filter(
        recipient=user, tag=Notification.TAG_SKILL_NUDGE, is_read=False
    ).exists()
    if not already_exists:
        Notification.objects.create(
            recipient=user,
            verb=str(SKILL_NUDGE_TEXT),
            link=reverse("skills:userskill_add"),
            tag=Notification.TAG_SKILL_NUDGE,
        )


@receiver(post_save, sender="skills.UserSkill")
@receiver(post_save, sender="skills.SkillWish")
def dismiss_skill_nudge_on_skill_added(sender, instance, created, **kwargs):
    if not created or not instance.user_id:
        return
    from notifications.models import Notification
    Notification.objects.filter(
        recipient_id=instance.user_id, tag=Notification.TAG_SKILL_NUDGE, is_read=False
    ).update(is_read=True)
