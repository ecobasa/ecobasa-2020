from django import template
from gifts.models import Listing
import re

register = template.Library()


@register.simple_tag
def find_listing_by_title(subject):
    """Return a `Listing` whose title exactly matches `subject`, or None.

    This is a best-effort helper used in message views where the message
    subject was set to a listing title (e.g., when contacting about a listing).
    """
    if not subject:
        return None
    try:
        return Listing.objects.filter(title=subject).first()
    except Exception:
        return None


@register.simple_tag
def find_listing_by_body(body):
    """Return a `Listing` whose random_id appears as a `Listing-ID: <id>` line in `body`, or None.

    Matches lines like "Listing-ID: taojvezn" (whitespace tolerant).
    """
    if not body:
        return None
    try:
        m = re.search(r"Listing-ID:\s*([A-Za-z0-9-_]+)", body)
        if not m:
            return None
        random_id = m.group(1)
        return Listing.objects.filter(random_id=random_id).first()
    except Exception:
        return None
