from django import template
from gifting.models import Ad
import re

register = template.Library()


@register.simple_tag
def find_ad_by_title(subject):
    """Return an `Ad` whose title exactly matches `subject`, or None.

    This is a best-effort helper used in message views where the message
    subject was set to an ad title (e.g., when contacting about an ad).
    """
    if not subject:
        return None
    try:
        return Ad.objects.filter(title=subject).first()
    except Exception:
        return None


@register.simple_tag
def find_ad_by_body(body):
    """Return an `Ad` whose random_id appears as an `Ad-ID: <id>` line in `body`, or None.

    Matches lines like "Ad-ID: taojvezn" (whitespace tolerant).
    """
    if not body:
        return None
    try:
        m = re.search(r"Ad-ID:\s*([A-Za-z0-9-_]+)", body)
        if not m:
            return None
        random_id = m.group(1)
        return Ad.objects.filter(random_id=random_id).first()
    except Exception:
        return None
