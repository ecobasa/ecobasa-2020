from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import get_language, gettext as _

from events import kinds
from events.filters import count_coming
from events.models import Event
from gift_economy.references.models import Reference, with_card_data

from . import contact as contact_form

HOMEPAGE_REFERENCES = 3
HOMEPAGE_ONLINE_CIRCLES = 6


def _ended(event, now):
    """Over by its hours already, on its last day (in its timezone; past midnight it ends
    the day after)."""
    if not (event.ends_on and event.ends_at):
        return False
    end = datetime.combine(event.ends_on, event.ends_at, tzinfo=event.zone)
    if event.starts_at and event.ends_at <= event.starts_at:
        end += timedelta(days=1)
    return end <= now


def online_gift_circles(language):
    """The next online gift-circles for anyone anywhere (those for people around a town are
    on the map). Those spoken in `language` first, then the soonest."""
    circles = list(
        Event.objects.current().filter(kind=kinds.GIFT_CIRCLE, is_online=True, location=None)
        .select_related("community", "host_user", "host_tour__organiser")
    )
    now = timezone.now()
    circles = [event for event in circles if not _ended(event, now)]
    circles.sort(key=lambda event: (language not in event.languages, event.starts_on or date.max, event.starts_at or time.min))
    circles = circles[:HOMEPAGE_ONLINE_CIRCLES]
    count_coming(circles)
    return circles


def homepage(request):
    # A different few each visit of the references staff featured (from those their
    # authors agreed to share)
    featured = with_card_data(
        Reference.objects.filter(share_publicly=True, pending=False, featured_at__isnull=False)
    ).order_by("?")[:HOMEPAGE_REFERENCES]
    return render(request, "homepage/homepage.html", {
        "featured_references": featured,
        "online_circles": online_gift_circles(get_language()),
    })

def support(request):
    return render(request, "homepage/support.html")


def contact(request):
    form = contact_form.ContactForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        if form.send():
            messages.success(request, _("Thank you! Your message is on its way to us."))
            return redirect("homepage:contact")
        form.add_error(None, _("Your message could not be sent right now. Please try again later."))
    return render(request, "homepage/contact.html", {"form": form})
