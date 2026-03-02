from django import template
from django.db.models import Q
from postman.models import Message

register = template.Library()


@register.simple_tag
def conversation_messages(message):
    """Return queryset of messages in the same thread as `message`, ordered by `sent_at`.

    Behavior:
    - If `message.thread` is set, use that as the thread root.
    - Otherwise treat `message` as the root and include any messages with `thread=message`.
    """
    if not message:
        return Message.objects.none()

    root = getattr(message, "thread", None) or message
    qs = Message.objects.filter(Q(thread=root) | Q(pk=root.pk)).order_by("sent_at")
    return qs
