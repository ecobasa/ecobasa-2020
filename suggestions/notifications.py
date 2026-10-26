from django.urls import reverse
from django.utils import timezone


def notify_new_suggestions(users):
    """Tell each user about their new suggestions in the notifications: one notification
    that counts what's new, moved back to the top rather than piling up while unread."""
    from notifications.models import Notification

    for user in users:
        bumped = Notification.objects.filter(
            recipient=user, tag=Notification.TAG_SUGGESTION, is_read=False,
        ).update(created_at=timezone.now())
        if not bumped:
            notification = Notification(recipient=user, tag=Notification.TAG_SUGGESTION, link=reverse("suggestions:list"))
            notification.verb = notification.text[:255]
            notification.save()
