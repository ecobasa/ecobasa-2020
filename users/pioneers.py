"""Pioneers: the members on a map and in a list, to find people to invite to a
gift-circle, a tour or a community, or to travel with. Members only, and only those who
show themselves (User.shows_on_map), each about where they live (users.places)."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.gis.db.models import GeometryField, PointField
from django.contrib.gis.db.models.functions import Distance, SnapToGrid
from django.core.paginator import Paginator
from django.db.models import F, Prefetch, Q
from django.db.models.functions import Cast
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from dashboard_lists import query_url
from events.filters import _bbox, _list, _point
from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import Skill, skill_name_q

from .models import User
from .places import CELL, approximate, town

# Pins per map request, the most recently active first
MAX_MARKERS = 500


def _skill_offers():
    return Listing.objects.current().filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, community=None)


def _skill_wishes():
    return Listing.objects.current().filter(type=Listing.TYPE_WISH, kind=Listing.KIND_SKILL, community=None)


def _any_skill(names):
    wanted = Q()
    for name in names:
        wanted |= skill_name_q(name)
    return wanted


def _spot():
    """Where a person is for filtering and sorting: the centre of their cell, so no
    search finds out more than the map shows (users.places)."""
    return SnapToGrid(Cast("location", GeometryField(srid=4326)), CELL)


def pioneers():
    """Everyone on the map: active, confirmed, with a place, not hidden."""
    return User.objects.filter(is_active=True, email_confirmed=True, shows_on_map=True, location__isnull=False)


class PioneerFilters:
    """The filters of the pioneer map and list, from the query string: a search (name,
    about them, skills they offer), a country, skills they offer and skills they want to
    learn (any of them), looking for a community, open to tour suggestions. `near` (lat,lng) is where distances are measured
    from, `bbox` the map's visible area, `invite` the invitation page someone picks for."""

    FLAGS = ("looking", "tours")

    def __init__(self, request):
        params = request.GET
        self.q = (params.get("q") or "").strip()
        country = (params.get("country") or "").strip().upper()
        self.country = country if len(country) == 2 and country.isalpha() else ""
        self.skills = [name.strip('"') for name in _list(params.get("skills")) if name.strip('"')]
        self.learn = [name.strip('"') for name in _list(params.get("learn")) if name.strip('"')]
        self.looking, self.tours = (params.get(flag) == "1" for flag in self.FLAGS)
        self.near = _point(params.get("near"))
        self.bbox = _bbox(params.get("bbox"))
        self.invite = invite_page(request, params.get("invite"))

    def apply(self, people):
        if self.q:
            offering = _skill_offers().filter(Q(title__icontains=self.q) | skill_name_q(self.q))
            people = people.filter(
                Q(name__icontains=self.q) | Q(about__icontains=self.q) | Q(pk__in=offering.values("owner_id"))
            )
        if self.country:
            people = people.filter(country=self.country)
        if self.skills:
            people = people.filter(pk__in=_skill_offers().filter(_any_skill(self.skills)).values("owner_id"))
        if self.learn:
            people = people.filter(pk__in=_skill_wishes().filter(_any_skill(self.learn)).values("owner_id"))
        if self.looking:
            people = people.filter(looking_for_community=True)
        if self.tours:
            people = people.filter(Q(tours_paused_until=None) | Q(tours_paused_until__lt=timezone.localdate()))
        return people

    def invite_url(self, person):
        """The invitation page with `person` picked, when one came to pick someone."""
        if not self.invite:
            return ""
        return f"{self.invite}{'&' if '?' in self.invite else '?'}{urlencode({'user': person.pk})}"


def invite_page(request, url):
    """`url` if it's a page of this site, else ""."""
    if url and url.startswith("/") and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}):
        return url
    return ""


def map_link(invite, point=None):
    """The pioneer map to pick someone for the invitation page `invite`, around `point`
    (where one invites to), if there is one."""
    params = {"invite": invite}
    if point is not None:
        params["near"] = f"{point.y:.2f},{point.x:.2f}"
    return f"{reverse('pioneers:list')}?{urlencode(params)}"


def _with_skills(people):
    return people.prefetch_related(
        Prefetch("listings", queryset=_skill_offers().select_related("skill").order_by("skill__name"), to_attr="skill_offers"),
        Prefetch("listings", queryset=_skill_wishes().select_related("skill").order_by("skill__name"), to_attr="skill_wishes"),
    )


@login_required
def pioneer_list(request):
    """Pioneers on a map, the list in a modal, with a search and filters, as on the
    communities and gifts, starting on the whole world."""
    from django_countries import countries as all_countries

    filters = PioneerFilters(request)
    codes = pioneers().exclude(country="").exclude(country=None).values_list("country", flat=True).distinct()
    countries = sorted(
        ((code, all_countries.name(code)) for code in codes if all_countries.name(code)), key=lambda pair: pair[1],
    )
    return render(request, "pioneers/pioneer_list.html", {
        "filters": filters,
        "countries": countries,
        "flag_choices": [
            ("looking", _("Looking for a community"), "fa-door-open"),
            ("tours", _("Open to tour suggestions"), "fa-route"),
        ],
        "layer_choices": [("ecobasa", _("ecobasa")), ("osm", _("OpenStreetMap")), ("satellite", _("Satellite"))],
    })


@login_required
def api_list(request):
    """The list in the modal, for htmx: nearest where one asked (or one's own place)
    first, else the most recently active."""
    filters = PioneerFilters(request)
    people = _with_skills(filters.apply(pioneers()))
    origin = filters.near or request.user.location
    if origin is not None:
        spot = Cast(_spot(), PointField(geography=True, srid=4326))
        people = people.annotate(distance=Distance(spot, origin)).order_by("distance", F("last_seen").desc(nulls_last=True))
    else:
        people = people.order_by(F("last_seen").desc(nulls_last=True), "name")
    # Scrolled on 20 at a time, as on the communities and gifts
    page = Paginator(people, 20).get_page(request.GET.get("page"))
    for person in page:
        person.place = town(person.location_name)
        person.km = round(person.distance.km) if origin is not None else None
        person.invite_url = filters.invite_url(person)
    return render(request, "pioneers/_results.html", {
        "page": page, "people": page.object_list, "sorted_by_distance": origin is not None,
        "next_url": query_url(request, page=page.next_page_number()) if page.has_next() else "",
    })


@login_required
def api_markers(request):
    """GeoJSON of the pioneers of the filters in the map's visible area (bbox), each
    somewhere in their cell, with what their popup shows."""
    filters = PioneerFilters(request)
    people = filters.apply(pioneers())
    if filters.bbox is not None:
        people = people.annotate(spot=_spot()).filter(spot__within=filters.bbox)
    people = _with_skills(people.order_by(F("last_seen").desc(nulls_last=True)))[:MAX_MARKERS]
    features = []
    for person in people:
        point = approximate(person.location, person.pk)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
            "properties": {
                "name": person.name or person.username or "",
                "url": person.get_absolute_url(),
                "image": person.image.url if person.image else "",
                "place": town(person.location_name) or "",
                "about": Truncator(person.about or "").chars(150),
                "skills": [listing.display_title for listing in person.skill_offers][:5],
                "learn": [listing.display_title for listing in person.skill_wishes][:5],
                "looking": person.looking_for_community,
                "active": render_to_string("events/_freshness.html", {"when": person.last_active}).strip(),
                "invite": filters.invite_url(person) if person != request.user else "",
                "own": person == request.user,
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features})


@login_required
def api_suggest(request):
    """Suggestions for the search: pioneers' names and the skills they offer."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    suggestions, seen = [], set()

    def add(value, kind):
        if value and value.lower() not in seen and len(suggestions) < 10:
            seen.add(value.lower())
            suggestions.append({"value": value, "type": kind})

    for name in pioneers().filter(name__icontains=q).order_by("name").values_list("name", flat=True)[:5]:
        add(name, "name")
    offers = _skill_offers().filter(owner__in=pioneers())
    for skill in Skill.objects.filter(skill_name_q(q, ""), listings__in=offers).distinct()[:5]:
        add(skill.get_name(), "skill")
    return JsonResponse(suggestions, safe=False)
