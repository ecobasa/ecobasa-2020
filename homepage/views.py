from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.db.models import F
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils import timezone
from django.utils.translation import get_language, gettext as _

from events import kinds
from events.filters import count_coming
from events.models import Event
from gift_economy.references.models import Reference, with_card_data
from tours.models import Tour

from . import contact as contact_form

# Each a slider showing three at a time
HOMEPAGE_REFERENCES = 9
HOMEPAGE_ONLINE_CIRCLES = 9
HOMEPAGE_TOURS = 9
# What the search overview shows of each list
SEARCH_PREVIEW = 3


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


def next_tours():
    """The tours in the list that are not over: the soonest first, then tour ideas, the
    freshest first."""
    return (
        Tour.objects.listed().current()
        .select_related("organiser")
        .prefetch_related("stops__event__community", "stops__community__photos", "learn_skills")
        .order_by(F("starts_on").asc(nulls_last=True), "-updated_at")[:HOMEPAGE_TOURS]
    )


def homepage(request):
    # A different few each visit of the references staff featured (from those their
    # authors agreed to share)
    featured = with_card_data(
        Reference.objects.filter(share_publicly=True, pending=False, featured_at__isnull=False)
    ).order_by("?")[:HOMEPAGE_REFERENCES]
    return render(request, "homepage/homepage.html", {
        "featured_references": featured,
        "online_circles": online_gift_circles(get_language()),
        "tours": next_tours(),
    })

def search(request):
    """The search of the homepage, in the communities, gifts, tours and events lists (and,
    logged in, the pioneers) at once: with hits in one of them straight to that list, with
    hits in several an overview of the first few of each, with a link to its list."""
    from communities.models import Community
    from communities.views import _current_events, _search_q, _skill_offers
    from events.filters import EventFilters
    from events.views import _events
    from gift_economy.gifts.views import filtered_listings
    from tours.geo import TourFilters
    from tours.views import _tours
    from users.pioneers import PioneerFilters, _with_skills, pioneers
    from users.places import town

    q = (request.GET.get("q") or "").strip()
    if not q:
        return redirect(reverse("homepage:homepage") + "#explore")
    events = EventFilters({"q": q}, request.user)
    tours = TourFilters({"q": q}, request.user)
    sections = [
        # (key, its list, the parameter its search reads, what was found)
        ("communities", "communities:list", "q", Community.objects.filter(_search_q(q)).distinct().prefetch_related("photos", _skill_offers(), _current_events()).order_by("name")),
        ("gifts", "gifts:search", "search", filtered_listings({"search": q}, require_location=False).order_by("-created_at")),
        ("tours", "tours:list", "q", tours.apply(tours.base(_tours())).order_by(F("starts_on").asc(nulls_last=True), "-updated_at")),
        ("events", "events:list", "q", events.apply(events.base(_events())).order_by(F("starts_on").asc(nulls_last=True))),
    ]
    if request.user.is_authenticated:
        people = PioneerFilters(request).apply(pioneers())
        sections.append(("pioneers", "pioneers:list", "q", _with_skills(people).order_by(F("last_seen").desc(nulls_last=True), "name")))
    found = []
    for key, list_name, param, items in sections:
        count = items.count()
        if count:
            found.append({
                "key": key, "count": count, "items": list(items[:SEARCH_PREVIEW]),
                "url": reverse(list_name) + "?" + urlencode({param: q}),
            })
    if len(found) == 1:
        return redirect(found[0]["url"])
    for section in found:
        if section["key"] == "events":
            count_coming(section["items"])
        if section["key"] == "pioneers":
            for person in section["items"]:
                person.place, person.km = town(person.location_name), None
    return render(request, "homepage/search.html", {"q": q, "sections": found})


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
