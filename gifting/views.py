from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.core.paginator import Paginator
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Polygon
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

from .forms import AdForm
from .filters import AdFilter
from .models import Ad
from communities.models import Community


def search(request):
    """Show all ads with filter ability"""
    f = AdFilter(request.GET, queryset=Ad.objects.none(), request=request)

    return render(request, "gifting/search.html", {"f": f})


def detail(request, pk):
    """Show details for an Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    return render(request, "gifting/ad_detail.html", {"ad": ad})


@login_required
def create(request):
    """Create a new Ad"""
    form = AdForm()
    if request.method == "POST":
        form = AdForm(request.POST, request.FILES)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.owner = request.user
            form.save()
            messages.success(
                request, _("%(ad_type)s created") % {"ad_type": ad.get_type_display()}
            )
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifting/ad_form.html", {"form": form})


def edit(request, pk):
    """Edit an existing Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    if not ad.owner == request.user:
        return redirect("/users/login?next=%s" % request.path)

    form = AdForm(instance=ad)
    if request.method == "POST":
        form = AdForm(request.POST, request.FILES, instance=ad)
        if form.is_valid():
            form.save()
            ad = form.instance
            messages.success(request, _("changes saved"))
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifting/ad_form.html", {"form": form, "ad": ad})


def delete(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    if not ad.owner == request.user:
        return redirect("/users/login?next=%s" % request.path)

    if request.method == "POST":
        ad.delete()
        messages.success(
            request, _("%(ad_type)s deleted") % {"ad_type": ad.get_type_display()}
        )
        return redirect(reverse("gifting:search"))
    else:
        return render(request, "gifting/ad_delete_confirm.html", {"ad": ad})


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


def _filtered_ads(request):
    """
    Run the full AdFilter pipeline (same as the main search view) so
    the API endpoints honour identical filter params: q, type, categories,
    from_me, location (distance ordering), location_name.
    """
    base_qs = Ad.objects.filter(location__isnull=False).select_related("owner")
    f = AdFilter(request.GET, queryset=base_qs, request=request)
    return f.qs


def _skill_communities(request):
    """
    Communities whose skills match ?q=, used as supplementary results.
    Only returned when no type filter is active (skills aren't offers/wishes).
    """
    # Suppress skill results if the user is filtering by ad type
    if request.GET.getlist("type"):
        return Community.objects.none()

    qs = Community.objects.filter(
        location__isnull=False,
        skills__isnull=False,
    ).prefetch_related("skills", "photos").distinct()

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(skills__name__icontains=q)

    return qs


# ── Endpoints ────────────────────────────────────────────────────────

@require_GET
def gifting_markers(request):
    """
    GeoJSON FeatureCollection — Ad markers + community skill markers
    within the current map viewport bounding box.

    Each feature carries a `source` property ('ad' | 'skill') so the
    frontend can render different marker icons.

    Query params (all optional):
        bbox        west,south,east,north  (WGS84)
        q           search term
        type        ad type filter (repeatable)
        categories  category id filter (repeatable)
        location    lat,lon  → distance-ordered results via AdFilter
        from_me     truthy → only current user's ads
    """
    bbox_param = request.GET.get("bbox", "")
    features   = []

    # ── Ad features ──────────────────────────────────────────────────
    ad_qs = _apply_bbox(_filtered_ads(request), bbox_param)

    for ad in ad_qs[:500]:
        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [ad.location.x, ad.location.y],
            },
            "properties": {
                "source":       "ad",
                "title":        ad.title,
                "description":  ad.description,
                "image":        ad.image.url if ad.image else None,
                "type_display": ad.get_type_display(),
                "url":          ad.get_absolute_url(),
            },
        })

    # ── Community skill features ─────────────────────────────────────
    skill_qs = _apply_bbox(_skill_communities(request), bbox_param)

    for community in skill_qs[:200]:
        first_photo = community.photos.first()
        skill_names = [s.name for s in community.skills.all()]
        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [community.location.x, community.location.y],
            },
            "properties": {
                "source":         "skill",
                "title":          ", ".join(skill_names[:3]),
                "description":    community.description,
                "image":          first_photo.image.url if first_photo and first_photo.image else None,
                "type_display":   "Skill / Teaching",
                "url":            community.get_absolute_url(),
                "community_name": community.name,
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def gifting_list_partial(request):
    page_num = int(request.GET.get("page", 1))

    ads_queryset = _filtered_ads(request)

    location_data = request.GET.get('location')
    if location_data and ',' in location_data:
        try:
          lat_str, lon_str = location_data.split(',')
          lat = float(lat_str)
          lon = float(lon_str)
          pnt = Point(lon, lat, srid=4326)

          ads_queryset = ads_queryset.annotate(
              distance=Distance('location', pnt)
          ).filter(location__distance_lte=(pnt, D(km=100))).order_by('distance')

        except (ValueError, TypeError, IndexError):
            ads_queryset = ads_queryset.order_by("-created_at")
    else:
        ads_queryset = ads_queryset.order_by("-created_at")

    paginator = Paginator(ads_queryset, 20)
    page = paginator.get_page(page_num)

    skill_communities = []
    if page_num == 1:
        skill_communities = list(_skill_communities(request)[:10])

    return render(request, "gifting/_gifting_list_partial.html", {
        "ads":               page,
        "skill_communities": skill_communities,
        "has_next":          page.has_next(),
        "next_page":         page.next_page_number() if page.has_next() else None,
        "total":             paginator.count,
        "q":                 request.GET.get("q", ""),
    })


@require_GET
def gifting_suggest(request):
    """
    Autocomplete JSON — merges ad titles with community skill names.
    Returns [{value, type}]  where type is 'ad' | 'skill'.

    The frontend renders a graduation-cap icon for skill suggestions.
    """
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)

    suggestions = []
    seen        = set()

    def add(value, kind):
        if value and value not in seen:
            seen.add(value)
            suggestions.append({"value": value, "type": kind})

    # Ad titles
    for title in (
        Ad.objects
        .filter(title__icontains=q)
        .values_list("title", flat=True)[:5]
    ):
        add(title, "ad")

    # Community skill names
    for skill in (
        Community.objects
        .filter(skills__name__icontains=q)
        .values_list("skills__name", flat=True)
        .distinct()[:5]
    ):
        add(skill, "skill")

    return JsonResponse(suggestions[:8], safe=False)
