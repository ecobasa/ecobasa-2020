import json

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from .models import Community
from .models import CommunityPhoto
from .forms import CommunityForm
from skills.models import CommunitySkill, Skill, SkillWish, UserSkill

from django.contrib.gis.geos import Polygon, Point
from django.contrib.gis.db.models.functions import Distance
from django.core.paginator import Paginator
from django.http import JsonResponse


def index(request):
    """Map-first list of communities."""
    from django_countries.fields import Country as DjangoCountry
    base_qs = Community.objects.all().prefetch_related("photos", "skills").order_by("name")

    countries_raw = (
        Community.objects
        .filter(country__isnull=False)
        .exclude(country='')
        .values_list('country', flat=True)
        .distinct()
    )
    countries = sorted(
        [(str(c), DjangoCountry(str(c)).name) for c in countries_raw if c and DjangoCountry(str(c)).name],
        key=lambda x: x[1]
    )

    communities = base_qs
    q = (request.GET.get("q") or "").strip()
    if q:
        communities = communities.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(location_name__icontains=q)
            | Q(skills__name__icontains=q)
        ).distinct()
    country = (request.GET.get('country') or '').strip()
    if country:
        communities = communities.filter(country=country)



    return render(
        request,
        "communities/community_list.html",
        {
            "communities": communities,
            "q": q,
            "countries": countries,
            "community_types": Community.COMMUNITY_TYPE_CHOICES,
            "community_statuses": Community.COMMUNITY_STATUS_CHOICES,
        },
    )


def detail(request, slug):
    """Show Community page"""
    community = get_object_or_404(Community, slug=slug)
    photos = list(community.photos.all())
    hero_image = photos[0].image.url if photos else None
    community_skills = list(community.community_skills.select_related("skill").order_by("skill__name"))
    skill_wishes = list(community.skill_wishes.select_related("skill").order_by("skill__name"))

    # Build a {skill_id: level_display} map for the visiting user so the modal can show their level
    user_levels_json = "{}"
    if request.user.is_authenticated and request.user != community.owner:
        skill_ids = [cs.skill_id for cs in community_skills] + [sw.skill_id for sw in skill_wishes]
        user_levels_json = json.dumps({
            str(us.skill_id): us.get_level_display()
            for us in UserSkill.objects.filter(user=request.user, skill_id__in=skill_ids)
        })

    return render(request, "communities/community_detail.html", {
        "community":        community,
        "photos":           photos,
        "hero_image":       hero_image,
        "community_skills": community_skills,
        "skill_wishes":     skill_wishes,
        "user_levels_json": user_levels_json,
    })


@login_required
@require_POST
def volunteer_request(request, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    owner = community.owner
    if not owner:
        messages.error(request, _("This community has no contact person."))
        return redirect(community.get_absolute_url())

    volunteer_mode  = request.POST.get("volunteer_mode", "")
    practice_skills = request.POST.get("practice_skills", "").strip()
    sender_skills   = request.POST.get("sender_skills", "").strip()
    stay_from       = request.POST.get("stay_from", "")
    stay_to         = request.POST.get("stay_to", "")
    msg_body        = request.POST.get("body", "").strip()

    if volunteer_mode == "wish":
        subject = str(_("Volunteer stay request — skills to offer at %(c)s") % {"c": community.name})
    elif volunteer_mode == "offer":
        subject = str(_("Volunteer stay request — skills to practice at %(c)s") % {"c": community.name})
    else:
        subject = str(_("Volunteer stay request at %(c)s") % {"c": community.name})

    full_body = msg_body
    if practice_skills:
        label = str(_("Skills I can help with") if volunteer_mode == "wish" else _("Skills I want to learn and practice at your place"))
        full_body += f"\n\n{label}:\nSkills: {practice_skills}"
    if sender_skills:
        full_body += f"\n\n{_('My skills')}:\nSender-Skills: {sender_skills}"
    if stay_from or stay_to:
        full_body += f"\n\n{_('Requested stay:')}\n"
        if stay_from:
            full_body += f"{_('From')} {stay_from}\n"
        if stay_to:
            full_body += f"{_('To')} {stay_to}\n"

    # Create postman message
    from postman.models import Message
    from django.utils.timezone import now as tz_now
    from django.urls import reverse
    pm = Message(
        subject=subject,
        body=full_body,
        sender=request.user,
        recipient=owner,
        sent_at=tz_now(),
        moderation_status="a",
    )
    pm.save()
    pm.thread = pm
    pm.save(update_fields=["thread"])

    # In-app notification for the community owner
    from notifications.models import Notification
    actor_name = request.user.name or request.user.username
    Notification.objects.create(
        recipient=owner,
        actor=request.user,
        verb=str(_("%(name)s requested a volunteering stay at %(community)s") % {
            "name": actor_name,
            "community": community.name,
        }),
        link=reverse("postman:inbox"),
        tag="volunteer_request",
    )

    if request.headers.get("HX-Request"):
        from django.http import HttpResponse
        actor_name_safe = (request.user.name or request.user.username)
        return HttpResponse(
            f'<div class="py-8 text-center">'
            f'<i class="fa-solid fa-campground text-4xl text-primary mb-3 block"></i>'
            f'<p class="font-semibold text-primary text-lg">'
            + str(_("Request sent!")) +
            f'</p>'
            f'<p class="text-sm text-brown mt-1">'
            + str(_("Your message has been delivered to %(community)s.") % {"community": community.name}) +
            f'</p></div>'
        )

    messages.success(request, str(_("Your request has been sent to %(community)s!") % {"community": community.name}))
    return redirect(community.get_absolute_url())


def _sync_community_skill_wishes(community, form):
    wish_val = form.cleaned_data.get('skill_wishes', '') or ''
    community.skill_wishes.all().delete()
    for name in [s.strip() for s in wish_val.split(',') if s.strip()]:
        skill, _ = Skill.objects.get_or_create(name__iexact=name, defaults={"name": name})
        SkillWish.objects.create(community=community, skill=skill)


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
    """Community submission form — login required."""
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if request.method == "POST":
        form = CommunityForm(request.POST, request.FILES)
        if form.is_valid():
            community = form.save(commit=False)
            if request.user.is_authenticated:
                community.owner = request.user
            community.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            _sync_community_skill_wishes(community, form)
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

def delete(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not request.user.is_authenticated or (community.owner and request.user != community.owner and not request.user.is_staff):
        return redirect(community.get_absolute_url())
    if request.method == "POST":
        community.delete()
        messages.success(request, _("Community deleted."))
        return redirect("communities:list")
    return redirect(community.get_absolute_url())


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
            _sync_community_skill_wishes(community, form)
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
    country = request.GET.get("country", "").strip()
    if country:
        qs = qs.filter(country=country)
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

    country_param = request.GET.get("country", "").strip()
    if country_param:
        qs = qs.filter(country=country_param)

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
    HTML partial for the list modal — HTMX swaps into #community-modal-list.

    Supports:
        q         full-text search (name, description, location, skills)
        country   ISO country code filter (exact, from CountryField)
        type      community type filter (repeatable)
        status    community status filter (repeatable)
        location  lat,lon — when present, annotates with Distance and sorts
                  by proximity. No hard radius cap; results are ordered
                  nearest-first so the user naturally sees close ones first.
        page      page number for infinite scroll (default 1)
    """
    qs = _base_qs(request).prefetch_related("skills", "photos")

    # ── Proximity sorting ─────────────────────────────────────────────
    # When the user clicks "near me", the browser sends location=lat,lon.
    # We annotate with PostGIS Distance and order by it so nearby
    # communities float to the top without hiding distant ones entirely.
    proximity_sort = False
    location_param = request.GET.get("location", "").strip()
    if location_param and ',' in location_param:
        try:
            lat_str, lon_str = location_param.split(',', 1)
            user_point = Point(float(lon_str), float(lat_str), srid=4326)
            qs = qs.annotate(
                distance=Distance('location', user_point)
            ).order_by('distance')
            proximity_sort = True
        except (ValueError, TypeError):
            qs = qs.order_by('name')
    else:
        qs = qs.order_by('name')

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "communities/_community_list_modal.html", {
        "communities":    page,
        "has_next":       page.has_next(),
        "next_page":      page.next_page_number() if page.has_next() else None,
        "total":          paginator.count,
        "q":              request.GET.get("q", ""),
        "country":        request.GET.get("country", ""),
        "proximity_sort": proximity_sort,
    })

@require_GET
def community_suggest(request):
    """
    Autocomplete suggestions for the search input.

    Query params:
        q   partial search term (min 2 chars)

    Returns JSON list: [{value, type}]
    where type is one of 'name' | 'location' | 'skill' | 'description' | 'vision'.
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

    # Description / vision — one entry if any community matches either field
    if Community.objects.filter(Q(description__icontains=q) | Q(vision__icontains=q)).exists():
        suggestions.append({"value": q, "type": "text"})

    # Locations (split on comma to surface city/country parts)
    for loc in Community.objects.filter(location_name__icontains=q).values_list("location_name", flat=True)[:10]:
        for part in (loc or "").split(","):
            if q.lower() in part.lower():
                add(part.strip(), "location")
        if len(suggestions) >= 8:
            break

    # Skills attached to a Community
    for skill in (
        CommunitySkill.objects
        .filter(skill__name__icontains=q)
        .values_list("skill__name", flat=True)
        .distinct()[:5]
    ):
        add(skill, "skill")

    return JsonResponse(suggestions[:12], safe=False)
