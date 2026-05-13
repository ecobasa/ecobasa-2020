from django.db.models import Q, Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

from .models import Community
from .models import CommunityPhoto
from .forms import CommunityForm

from django.contrib.gis.geos import Polygon
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def index(request):
    """Map-first list of communities."""
    # base queryset (used to derive country options)
    base_qs = Community.objects.all().prefetch_related("photos", "skills").order_by("name")

    # compute available countries from location_name (last comma-separated part)
    countries = sorted({
        loc.split(',')[-1].strip()
        for loc in base_qs.values_list('location_name', flat=True)
        if loc
    })

    communities = base_qs
    q = (request.GET.get("q") or "").strip()
    if q:
        communities = communities.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(location_name__icontains=q)
            | Q(skills__name__icontains=q)
        ).distinct()
    # optional country filter
    country = (request.GET.get('country') or '').strip()
    if country:
        communities = communities.filter(location_name__icontains=country)


    return render(
        request,
        "communities/community_list.html",
        {
            "communities": communities,
            "q": q,
            "countries": countries,
            "selected_country": country,
            "community_types": Community.COMMUNITY_TYPE_CHOICES,
            "community_statuses": Community.COMMUNITY_STATUS_CHOICES,
        },
    )


def detail(request, slug):
    """Show Community page"""
    community = get_object_or_404(Community, slug=slug)
    photos = list(community.photos.all())
    hero_image = photos[0].image.url if photos else None
    return render(request, "communities/community_detail.html", {
        "community": community,
        "photos": photos,
        "hero_image": hero_image,
    })


def _collect_gallery_files(form, request):
    images = []
    cleaned = form.cleaned_data.get("gallery")
    if cleaned:
        if isinstance(cleaned, (list, tuple)):
            images.extend(cleaned)
        else:
            images.append(cleaned)
    # also read raw FILES to be safe with multi-file widgets
    for f in request.FILES.getlist("gallery"):
        if f not in images:
            images.append(f)
    return images


def create(request):
    """Public community submission form."""
    if request.method == "POST":
        form = CommunityForm(request.POST, request.FILES)
        if form.is_valid():
            community = form.save(commit=False)
            if request.user.is_authenticated:
                community.owner = request.user
            community.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            images = _collect_gallery_files(form, request)
            for image_file in images:
                CommunityPhoto.objects.create(community=community, image=image_file)
            if images:
                messages.success(request, _("Uploaded %(count)s image(s).") % {"count": len(images)})
            return redirect(community.get_absolute_url())
        else:
            messages.error(
                request,
                _("Form invalid: %(errors)s")
                % {"errors": "; ".join([f"{k}: {','.join(v)}" for k, v in form.errors.items()])},
            )
    else:
        form = CommunityForm()

    return render(
        request,
        "communities/community_form.html",
        {"form": form},
    )

def update(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not request.user.is_authenticated or (community.owner and request.user != community.owner and not request.user.is_staff):
        return redirect(community.get_absolute_url())

    if request.method == "POST":
        form = CommunityForm(request.POST, request.FILES, instance=community)
        if form.is_valid():
            community = form.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            delete_ids = request.POST.getlist("delete_photos")
            if delete_ids:
                community.photos.filter(id__in=delete_ids).delete()
            images = _collect_gallery_files(form, request)
            for image_file in images:
                CommunityPhoto.objects.create(community=community, image=image_file)
            if images:
                messages.success(request, _("Uploaded %(count)s image(s).") % {"count": len(images)})
            messages.success(request, _("Community updated."))
            return redirect(community.get_absolute_url())
        else:
            messages.error(
                request,
                _("Form invalid: %(errors)s")
                % {"errors": "; ".join([f"{k}: {','.join(v)}" for k, v in form.errors.items()])},
            )
    else:
        form = CommunityForm(instance=community)

    return render(
        request,
        "communities/community_form.html",
        {"form": form, "community": community},
    )


# ── Helpers ──────────────────────────────────────────────────────────

def _base_qs(request):
    """Return a Community queryset filtered by ?q= search term."""
    qs = Community.objects.filter(location__isnull=False)  # PostGIS point field
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(location_name__icontains=q) |
            Q(skills__name__icontains=q)
        )
    selected_types = request.GET.getlist("type")
    if selected_types:
        qs = qs.filter(type__in=selected_types)
    selected_statuses = request.GET.getlist("status")
    if selected_statuses:
        qs = qs.filter(status__in=selected_statuses)

    return qs.distinct()


# ── Endpoints ────────────────────────────────────────────────────────

@require_GET
def community_markers(request):
    """
    GeoJSON endpoint for OpenLayers map markers.

    Query params:
        bbox  west,south,east,north  (WGS84 degrees)
        q     search term            (optional)

    PostGIS filters by bounding box so we only ship the features
    currently visible in the viewport — not the whole dataset.

    Returns GeoJSON FeatureCollection.
    """
    # Define a custom prefetch for photos to only get the "hero" image
    hero_prefetch = Prefetch(
        "photos",
        queryset=CommunityPhoto.objects.order_by("id"), # Or your preferred order
        to_attr="hero_photos" # This stores the result in a list called 'hero_photos'
    )

    # Use the helper to get the base filtered queryset
    qs = _base_qs(request).prefetch_related(hero_prefetch, "skills")

    bbox_param = request.GET.get("bbox", "")
    if bbox_param:
        try:
            west, south, east, north = map(float, bbox_param.split(","))
            bbox_poly = Polygon.from_bbox((west, south, east, north))
            bbox_poly.srid = 4326
            qs = qs.filter(location__within=bbox_poly)
        except (ValueError, TypeError):
            pass  # ignore malformed bbox

    features = []
    for c in qs[:500]:  # hard cap per request
        first_photo = c.hero_photos[0] if c.hero_photos else None
        photo_url = first_photo.image.url if first_photo and first_photo.image else None
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                # .location is a PointField; adjust if you store lat/lon separately
                "coordinates": [c.location.x, c.location.y],
            },
            "properties": {
                "name":        c.name,
                "description": c.description,
                "vision":      c.vision,
                "image":       photo_url,
                "status":      c.get_status_display(),
                "type":        c.get_type_display(),
                "url":         c.get_absolute_url(),
                "inhabitants": c.inhabitants,
                "children":    c.children,
                "max_guests":  c.max_guests,
                "skills":      list(c.skills.values_list("name", flat=True)),
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def community_list_partial(request):
    """
    HTML partial for the list modal, rendered server-side.
    HTMX swaps this into #community-modal-list.

    Query params:
        q        search term   (optional)
        country  country name  (optional)
        page     page number   (default 1)

    The response also includes an OOB swap for the result count badge.
    """
    qs = _base_qs(request)

    country = request.GET.get("country", "").strip()
    if country:
        qs = qs.filter(location_country=country)  # adjust field name

    paginator = Paginator(qs.prefetch_related("skills", "photos"), 20)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "communities/_community_list_modal.html", {
        "communities": page,
        "has_next":    page.has_next(),
        "next_page":   page.next_page_number() if page.has_next() else None,
        "total":       paginator.count,
        "q":           request.GET.get("q", ""),
        "country":     country,
    })


@require_GET
def community_suggest(request):
    """
    Autocomplete suggestions for the search input.

    Query params:
        q   partial search term (min 2 chars)

    Returns JSON list: [{value, type}]
    where type is one of 'name' | 'location' | 'skill'.

    Uses DISTINCT + LIMIT so it's fast without a search index.
    """
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)

    suggestions = []
    seen = set()

    def add(value, kind):
        if value and value not in seen:
            seen.add(value)
            suggestions.append({"value": value, "type": kind})

    # Names
    for name in Community.objects.filter(name__icontains=q).values_list("name", flat=True)[:5]:
        add(name, "name")

    # Locations (split on comma to surface city/country parts)
    for loc in Community.objects.filter(location_name__icontains=q).values_list("location_name", flat=True)[:10]:
        for part in (loc or "").split(","):
            if q.lower() in part.lower():
                add(part.strip(), "location")
        if len(suggestions) >= 8:
            break

    # Filter tags that are actually attached to a Community via the 'skills' manager

    for skill in (
        Community.objects
        .filter(skills__name__icontains=q)
        .values_list("skills__name", flat=True)
        .distinct()[:5]
    ):
        add(skill, "skill")

    return JsonResponse(suggestions[:10], safe=False)
