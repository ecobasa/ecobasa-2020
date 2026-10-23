from django.urls import reverse
from django.utils.translation import gettext as _

from notifications.models import Notification


def notify_reference_created(reference):
    """Tell the person a new reference is about (or the ambassador, for a community or
    its skills), linking straight to it in their references dashboard."""
    recipient = reference.recipient
    if recipient is None or recipient == reference.author:
        return
    url = reverse("references:list")
    if reference.content_type.model in ("community", "communityskill"):
        subject = reference.subject
        community = subject.get_skill_holder() if hasattr(subject, "get_skill_holder") else subject
        url = f"{url}?community={community.slug}"
    Notification.objects.create(
        recipient=recipient,
        actor=reference.author,
        reference=reference,
        tag=Notification.TAG_REFERENCE,
        # Fallback only; the shown text is built in the reader's language
        verb=_("New reference"),
        link=f"{url}#reference-{reference.pk}",
    )
