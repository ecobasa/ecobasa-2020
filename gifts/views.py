import json
import re
import urllib.request
import urllib.parse
from datetime import datetime as _dt

from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.db.models import Prefetch, Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.db.models.functions import Distance
from django.views.decorators.http import require_GET
from django.core.cache import cache

from .forms import ListingForm
from .filters import NON_LISTING_TYPES, ListingFilter
from .models import Listing
from communities.models import Community
from projects.models import Need, Project
from users.models import User
from skills.models import UserSkill, CommunitySkill, Skill, skill_name_q
from matches.forms import MatchForm
from matches.emails import notify_match_created


def search(request):
    """Show all listings with filter ability"""
    f = ListingFilter(request.GET, queryset=Listing.objects.none(), request=request)

    return render(request, "gifts/search.html", {"f": f})


def detail(request, pk):
    """Show details for a Listing"""
    listing = get_object_or_404(Listing, pk=pk)
    context = {"listing": listing}

    if request.user.is_authenticated and request.user != listing.owner:
        if request.method == "POST":
            form = MatchForm(request.POST)
            if form.is_valid():
                match = form.save(commit=False)
                match.from_user = request.user
                match.recipient = listing.get_match_owner()
                match.target = listing
                match.save()
                notify_match_created(match, http_request=request)
                messages.success(request, _("Your request has been sent."))
                return redirect(match.get_absolute_url())
        else:
            form = MatchForm()
        context["form"] = form

    is_owner = request.user.is_authenticated and request.user == listing.owner
    context["is_owner"] = is_owner
    if is_owner:
        context["incoming_requests"] = list(listing.matches.select_related("from_user").order_by("-created_at")[:20])

    return render(request, "gifts/listing_detail.html", context)


@login_required
def create(request):
    """Create a new Listing"""
    form = ListingForm()
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            form.save()
            messages.success(
                request, _("%(listing_type)s created") % {"listing_type": listing.get_type_display()}
            )
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifts/listing_form.html", {"form": form})


def edit(request, pk):
    """Edit an existing Listing"""
    listing = get_object_or_404(Listing, pk=pk)
    if not listing.owner == request.user:
        return redirect("/users/login?next=%s" % request.path)

    form = ListingForm(instance=listing)
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES, instance=listing)
        if form.is_valid():
            form.save()
            listing = form.instance
            messages.success(request, _("changes saved"))
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifts/listing_form.html", {"form": form, "listing": listing})


def delete(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    if not listing.owner == request.user:
        return redirect("/users/login?next=%s" % request.path)

    if request.method == "POST":
        listing.delete()
        messages.success(
            request, _("%(listing_type)s deleted") % {"listing_type": listing.get_type_display()}
        )
        return redirect(reverse("gifts:search"))
    else:
        return render(request, "gifts/listing_delete_confirm.html", {"listing": listing})


# ── Shared helpers ───────────────────────────────────────────────────

def _apply_bbox(qs, bbox_param, location_field="location"):
    """Filter a queryset to features within the bbox string 'w,s,e,n'."""
    if not bbox_param:
        return qs
    try:
        west, south, east, north = map(float, bbox_param.split(","))
        poly = Polygon.from_bbox((west, south, east, north))
        poly.srid = 4326
        return qs.filter(**{f"{location_field}__within": poly})
    except (ValueError, TypeError):
        return qs


def _order_by_distance(qs, request, location_field="location"):
    """Sort nearest-first when a 'lat,lon' location param is given (same format as ListingFilter)."""
    try:
        lat, lon = map(float, request.GET.get("location", "").split(","))
    except ValueError:
        return qs
    loc = Point(lon, lat, srid=4326)
    return qs.annotate(distance=Distance(location_field, loc)).order_by("distance")


def _filtered_listings(request, require_location=True):
    types = request.GET.getlist("type")
    listing_types = [t for t in types if t not in NON_LISTING_TYPES]

    if types and not listing_types:
        return Listing.objects.none()

    base_qs = Listing.objects.select_related("owner")
    if require_location:
        base_qs = base_qs.filter(location__isnull=False)

    if len(listing_types) != len(types):
        data = request.GET.copy()
        data.setlist("type", listing_types)
        f = ListingFilter(data, queryset=base_qs, request=request)
    else:
        f = ListingFilter(request.GET, queryset=base_qs, request=request)

    return f.qs


def _skill_communities(request, require_location=True):
    types = request.GET.getlist("type")
    if types and "skill" not in types:
        return Community.objects.none()

    filters = {"community_skills__isnull": False}
    if require_location:
        filters["location__isnull"] = False

    qs = Community.objects.filter(**filters).prefetch_related("community_skills__skill", "photos").distinct()

    q = request.GET.get("search", "").strip()
    if q:
        qs = qs.filter(
            skill_name_q(q, "community_skills__skill__")
            | Q(community_skills__skill__description__icontains=q)
            | Q(community_skills__description__icontains=q)
            | Q(description__icontains=q)
        ).distinct()

    return _order_by_distance(qs, request)


def _skill_users(request, require_location=True):
    types = request.GET.getlist("type")
    if types and "skill" not in types:
        return User.objects.none()

    filters = {"user_skills__isnull": False}
    if require_location:
        filters["location__isnull"] = False

    qs = User.objects.filter(**filters).prefetch_related("user_skills__skill").distinct()

    q = request.GET.get("search", "").strip()
    if q:
        qs = qs.filter(
            skill_name_q(q, "user_skills__skill__")
            | Q(user_skills__skill__description__icontains=q)
            | Q(user_skills__description__icontains=q)
            | Q(about__icontains=q)
        ).distinct()

    return _order_by_distance(qs, request)


def _project_needs(request, require_location=True, bbox_param=""):
    """Current projects with open needs, nearest first: (project, open needs) pairs. With
    gift categories chosen, only needs in those categories count; with a search term, the
    needs matching it (or all of a project that matches it itself)."""
    types = request.GET.getlist("type")
    if types and "need" not in types:
        return []

    qs = Project.objects.current().select_related("community").prefetch_related(
        "community__photos",
        Prefetch("needs", queryset=Need.objects.select_related("skill", "category").prefetch_related("need_offers__match")),
    )
    if require_location:
        qs = qs.filter(community__location__isnull=False)
    qs = _apply_bbox(qs, bbox_param, "community__location")

    q = request.GET.get("search", "").strip()
    project_matches = set()
    if q:
        project_matches = set(qs.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(community__name__icontains=q)
        ).values_list("pk", flat=True))
        needs_q = Q(needs__title__icontains=q) | Q(needs__details__icontains=q) | skill_name_q(q, "needs__skill__")
        qs = qs.filter(Q(pk__in=project_matches) | needs_q).distinct()
    categories = {int(c) for c in request.GET.getlist("categories") if c.isdigit()}

    def matches(need):
        if categories and need.category_id not in categories:
            return False
        if q and not (
            q.lower() in need.title.lower() or q.lower() in need.details.lower()
            or q.lower() in need.display_title.lower()
        ):
            return False
        return True

    result = []
    for project in _order_by_distance(qs, request, "community__location"):
        needs = [need for need in project.needs.all() if not need.is_done]
        shown = [need for need in needs if matches(need)]
        if not shown and project.pk in project_matches and not categories:
            shown = needs
        if shown:
            result.append((project, shown))
    return result


# ── Endpoints ────────────────────────────────────────────────────────

def _public_name(user):
    """Name shown on public map popups; never falls back to the email address."""
    if not user:
        return ""
    return user.name or user.username or ""


@require_GET
def gifts_markers(request):
    """
    GeoJSON FeatureCollection — Listing markers + community skill markers
    within the current map viewport bounding box.

    Each feature carries a `source` property ('listing' | 'skill') so the
    frontend can render different marker icons.

    Query params (all optional):
        bbox        west,south,east,north  (WGS84)
        q           search term
        type        listing type filter (repeatable)
        categories  category id filter (repeatable)
        location    lat,lon  → distance-ordered results via ListingFilter
        from_me     truthy → only current user's listings
    """
    bbox_param = request.GET.get("bbox", "")
    features   = []

    # ── Listing features ─────────────────────────────────────────────
    listing_qs = _apply_bbox(_filtered_listings(request), bbox_param)

    for listing in listing_qs[:500]:
        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [listing.location.x, listing.location.y],
            },
            "properties": {
                "source":       "listing",
                "title":        listing.title,
                "description":  listing.description,
                "image":        listing.image.url if listing.image else None,
                "listing_type": listing.type,
                "amount":       listing.amount,
                "type_display": listing.get_type_display(),
                "url":          listing.get_absolute_url(),
                "user_name":    _public_name(listing.owner),
            },
        })

    q = request.GET.get("search", "").strip()

    def _matching_skills(skills, owner_text):
        """With a search term, keep only the skills that match it themselves,
        unless the owner's own text (about / description) already matched."""
        if not q or q.lower() in (owner_text or "").lower():
            return skills.all()
        return skills.select_related("skill").filter(
            skill_name_q(q)
            | Q(skill__description__icontains=q)
            | Q(description__icontains=q)
        )

    # ── Community skill features ─────────────────────────────────────
    skill_qs = _apply_bbox(_skill_communities(request), bbox_param)

    # One marker per skill, so every marker links to exactly one detail page.
    # Skills at the same spot are fanned out on the map.
    for community in skill_qs[:200]:
        first_photo = community.photos.first()
        for cs in _matching_skills(community.community_skills, community.description):
            features.append({
                "type": "Feature",
                "geometry": {
                    "type":        "Point",
                    "coordinates": [community.location.x, community.location.y],
                },
                "properties": {
                    "source":         "skill",
                    "title":          cs.skill.get_name(),
                    "description":    cs.description or community.description,
                    "image":          first_photo.image.url if first_photo and first_photo.image else None,
                    "type_display":   str(_("Skill / Teaching")),
                    "url":            cs.get_absolute_url(),
                    "community_name": community.name,
                },
            })

    # ── User skill features ──────────────────────────────────────────
    user_skill_qs = _apply_bbox(_skill_users(request), bbox_param)

    for user in user_skill_qs[:200]:
        for us in _matching_skills(user.user_skills, user.about):
            features.append({
                "type": "Feature",
                "geometry": {
                    "type":        "Point",
                    "coordinates": [user.location.x, user.location.y],
                },
                "properties": {
                    "source":       "user_skill",
                    "title":        us.skill.get_name(),
                    "description":  us.description or user.about or "",
                    "image":        user.image.url if user.image else None,
                    "type_display": str(_("User Skill")),
                    "url":          us.get_absolute_url(),
                    "user_name":    _public_name(user),
                },
            })

    # ── Project needs: one marker per project, listing its open needs ─
    for project, needs in _project_needs(request, bbox_param=bbox_param)[:200]:
        community = project.community
        photo = community.photos.first()
        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [community.location.x, community.location.y],
            },
            "properties": {
                "source":         "need",
                "title":          project.title,
                "description":    project.description,
                "image":          photo.image.url if photo and photo.image else None,
                "type_display":   str(_("Project needs")),
                "url":            project.get_absolute_url(),
                "community_name": community.name,
                "needs":          [
                    {"title": need.display_title, "amount": need.amount, "icon": need.icon} for need in needs
                ],
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def gifts_list_partial(request):
    page_num = int(request.GET.get("page", 1))

    listings_queryset = _filtered_listings(request, require_location=False)
    if not request.GET.get('location'):
        listings_queryset = listings_queryset.order_by("-created_at")

    paginator = Paginator(listings_queryset, 20)
    page = paginator.get_page(page_num)

    project_needs = _project_needs(request, require_location=False)
    sc_qs = _skill_communities(request, require_location=False)
    su_qs = _skill_users(request, require_location=False)

    skill_communities = []
    skill_users = []

    if page_num == 1:
        skill_communities = list(sc_qs[:10])
        skill_users = list(su_qs[:10])

    return render(request, "gifts/_gifts_list_partial.html", {
        "listings":          page,
        "skill_communities": skill_communities,
        "skill_users":       skill_users,
        "project_needs":     project_needs[:10] if page_num == 1 else [],
        "has_next":          page.has_next(),
        "next_page":         page.next_page_number() if page.has_next() else None,
        "total":             paginator.count + sc_qs.count() + su_qs.count() + len(project_needs),
        "q":                 request.GET.get("search", ""),
    })


@require_GET
def nominatim_proxy(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 3:
        return JsonResponse([], safe=False)
    cache_key = "nominatim:" + q.lower()
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached, safe=False)
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "format": "json", "addressdetails": "1", "limit": "10", "q": q,
        })
        req = urllib.request.Request(url, headers={"User-Agent": "ecobasa.org/1.0 geocoder"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        cache.set(cache_key, data, 86400)
        return JsonResponse(data, safe=False)
    except Exception:
        return JsonResponse([], safe=False)


@require_GET
def gifts_suggest(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)

    suggestions = []
    seen        = set()

    def add(value, kind):
        if value and value not in seen:
            seen.add(value)
            suggestions.append({"value": value, "type": kind})

    # Listing titles
    for listing in (
        Listing.objects
        .filter(title__icontains=q)
        .values('title', 'type')[:4]
    ):
        add(listing['title'], listing['type'])

    # Owner names — placed early so they aren't cut off by the 8-item limit
    for user in (
        User.objects
        .filter(Q(name__icontains=q) | Q(email__icontains=q), listings__isnull=False)
        .only("name", "email")
        .distinct()[:2]
    ):
        add(user.name or user.email, "owner")

    # Skill names held by communities or people, matched and shown in the active language
    for skill in (
        Skill.objects
        .filter(skill_name_q(q, ""))
        .filter(Q(community_skills__isnull=False) | Q(user_skills__isnull=False))
        .distinct()[:6]
    ):
        add(skill.get_name(), "skill")

    # Description match — extract words that start with the query
    def _desc_words(*texts):
        q_lower = q.lower()
        for text in texts:
            for word in re.findall(r'\b\w[\w-]*\b', text or ""):
                if word.lower().startswith(q_lower) and word.lower() != q_lower:
                    yield word.lower()

    for desc, in (
        Listing.objects
        .filter(Q(description__icontains=q))
        .exclude(title__icontains=q)
        .values_list("description")[:5]
    ):
        for word in _desc_words(desc):
            add(word, "text")

    for desc, skill_desc in (
        CommunitySkill.objects
        .filter(Q(description__icontains=q) | Q(skill__description__icontains=q))
        .exclude(skill_name_q(q))
        .values_list("description", "skill__description")[:5]
    ):
        for word in _desc_words(desc, skill_desc):
            add(word, "text")

    for desc, skill_desc in (
        UserSkill.objects
        .filter(Q(description__icontains=q) | Q(skill__description__icontains=q))
        .exclude(skill_name_q(q))
        .values_list("description", "skill__description")[:5]
    ):
        for word in _desc_words(desc, skill_desc):
            add(word, "text")

    return JsonResponse(suggestions[:8], safe=False)
