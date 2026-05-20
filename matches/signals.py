from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="matches.VolunteerRequest")
def sync_volunteer_skills_to_profile(sender, instance, created, **kwargs):
    if not created:
        return

    from skills.models import Skill, UserSkill, SkillWish
    from notifications.models import Notification

    user = instance.from_user
    new_offers = []
    new_wishes = []

    def _get_or_create_skill(name):
        name = name.strip()
        skill = Skill.objects.filter(name__iexact=name).first()
        if skill is None:
            skill, _ = Skill.objects.get_or_create(name=name)
        return skill

    for name in instance.sender_skills_list:
        skill = _get_or_create_skill(name)
        _, was_created = UserSkill.objects.get_or_create(user=user, skill=skill)
        if was_created:
            new_offers.append(skill.name)

    for name in instance.practice_skills_list:
        skill = _get_or_create_skill(name)
        wish, was_created = SkillWish.objects.get_or_create(user=user, skill=skill)
        if was_created:
            if instance.practice_skill_level:
                wish.level = instance.practice_skill_level
                wish.save(update_fields=["level"])
            new_wishes.append(skill.name)

    if not new_offers and not new_wishes:
        return

    parts = []
    if new_offers:
        parts.append(f"{len(new_offers)} skill{'s' if len(new_offers) != 1 else ''} added to your profile")
    if new_wishes:
        parts.append(f"{len(new_wishes)} skill {'wishes' if len(new_wishes) != 1 else 'wish'} added to your profile")

    Notification.objects.create(
        recipient=user,
        verb=f"Your volunteer application filled in your profile: {' and '.join(parts)}.",
        link=user.get_absolute_url(),
        tag="message",
    )
