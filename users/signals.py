from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


@receiver(user_logged_in)
def create_skill_nudge_notification(sender, request, user, **kwargs):
    has_skills = user.user_skills.exists() or user.skill_wishes.exists()
    if has_skills:
        return
    from notifications.models import Notification
    already_exists = Notification.objects.filter(
        recipient=user, tag=Notification.TAG_SKILL_NUDGE, is_read=False
    ).exists()
    if not already_exists:
        Notification.objects.create(
            recipient=user,
            verb=_(
                "Your profile has no skills yet — add what you can offer and "
                "what you want to learn or need help with so communities and "
                "people can find you."
            ),
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
