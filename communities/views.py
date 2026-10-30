import json
import re
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from .models import Community, public_location
from .models import CommunityPhoto
from .forms import CommunityForm
from gift_economy.gifts.models import Listing, skill_offers, sync_skill_listings
from gift_economy.gifts.skills.models import Skill, skill_name_q, skill_slug_for_name

from django.contrib.gis.geos import Polygon, Point
from django.contrib.gis.db.models import PointField
from django.contrib.gis.db.models.functions import Distance
from django.db.models.functions import Cast
from users.places import town
from django.core.paginator import Paginator
from django.http import JsonResponse


def index(request):
    """Map-first list of communities."""
    from django_countries.fields import Country as DjangoCountry
    base_qs = Community.objects.all().prefetch_related("photos", _skill_offers()).order_by("name")

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
        communities = communities.filter(_search_q(q)).distinct()
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
    listings = Listing.objects.of(community).current().select_related("skill", "project")
    # Skills you can learn here, also in its current projects (each skill once)
    community_skills = list({
        listing.skill_id: listing
        for listing in sorted(
            listings.filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL),
            key=lambda listing: listing.project_id is None,  # its own listing wins over a project's
        )
    }.values())
    community_skills.sort(key=lambda listing: listing.display_title)
    # Its members' skills join them, each skill once (the community's own listing wins);
    # their other offers are listed as the community's gifts
    members = community.members()
    member_offers = list(
        Listing.objects.open().filter(owner__in=members, community=None, type=Listing.TYPE_OFFER)
        .exclude(type=Listing.TYPE_OFFER, skill__isnull=False, available=False).select_related("owner", "skill")
    )
    holders = {}
    for offer in member_offers:
        if offer.kind == Listing.KIND_SKILL:
            holders.setdefault(offer.skill_id, []).append(offer)
    skills = [(listing, [o.owner for o in holders.pop(listing.skill_id, [])]) for listing in community_skills]
    skills += [(offers[0], [o.owner for o in offers]) for offers in holders.values()]
    skills.sort(key=lambda pair: pair[0].display_title)
    things = sorted(
        [l for l in listings.filter(type=Listing.TYPE_OFFER, project=None).exclude(kind=Listing.KIND_SKILL)]
        + [o for o in member_offers if o.kind != Listing.KIND_SKILL],
        key=lambda listing: listing.display_title,
    )
    # What the community and its members lend (its tool library), apart from the gifts,
    # each with whether it is lent right now
    library = [listing for listing in things if listing.lends_out]
    # Its seeds and plants (a seed library), apart from the other gifts
    seeds_plants = [listing for listing in things if listing.kind == Listing.KIND_SEEDS_PLANTS]
    gifts = [listing for listing in things if not listing.lends_out and listing.kind != Listing.KIND_SEEDS_PLANTS]
    for listing in library:
        listing.lent_now_loan = listing.lent_now()
    skill_wishes = sorted(
        listings.filter(type=Listing.TYPE_WISH, project=None).exclude(skill=None), key=lambda listing: listing.display_title,
    )

    # Build a {skill_id: level_display} map for the visiting user so the modal can show their level
    user_levels_json = "{}"
    help_wish = learn_skill = None
    if request.user.is_authenticated and request.user != community.owner:
        # ?help=<skill slug> (from a suggestion) opens the volunteer form for that wish,
        # ?learn=<skill slug> (from a skill's page) for learning that skill here
        help_wish = next((sw for sw in skill_wishes if sw.skill.slug == request.GET.get("help")), None)
        learn_skill = next((cs for cs in community_skills if cs.skill.slug == request.GET.get("learn")), None)
        skill_ids = [cs.skill_id for cs in community_skills] + [sw.skill_id for sw in skill_wishes]
        user_levels_json = json.dumps({
            str(us.skill_id): us.get_level_display()
            for us in skill_offers(request.user).filter(skill_id__in=skill_ids)
        })

    projects = (
        community.projects.select_related("community")
        .prefetch_related(Prefetch(
            "listings", queryset=Listing.objects.select_related("skill").prefetch_related("contributions__match"),
        ))
    )
    is_ambassador = request.user.is_authenticated and (request.user.is_staff or request.user == community.owner)

    shows_place = community.shows_place_to(request.user)
    place_name, place_point = community.place_for(request.user)
    return render(request, "communities/community_detail.html", {
        "community":        community,
        # Its exact place, address and phone number only for who may know (users.places)
        "shows_place":      shows_place,
        "place_name":       place_name,
        "place_point":      place_point,
        "projects":         projects.current(),
        # The ambassador also sees archived and ended projects, to bring one back
        "past_projects":    projects.exclude(pk__in=projects.current()).order_by("-updated_at")[:10] if is_ambassador else [],
        "is_ambassador":    is_ambassador,
        "photos":           photos,
        "hero_image":       hero_image,
        "community_skills": community_skills,
        # Each skill once, with the members who have it too; and the gifts on offer
        "skills":           skills,
        "gifts":            gifts,
        "library":          library,
        "seeds_plants":     seeds_plants,
        "learn_skill":      learn_skill,
        "skill_wishes":     skill_wishes,
        "user_levels_json": user_levels_json,
        "own_skill_names":  ", ".join(
            l.display_title for l in skill_offers(request.user).select_related("skill")
        ) if request.user.is_authenticated else "",
        "help_wish":        help_wish,
        # What the volunteer form offers to bring along: open needs of current projects
        # and the ambassador's gift wishes
        "bring_projects":   [(p, needs) for p in projects.current() if (needs := [n for n in p.needs() if not n.is_done])],
        "bring_wishes":     _community_wishes(community),
    })


def _community_wishes(community):
    """The community's wishes for things outside its projects that are still open."""
    return list(
        Listing.objects.of(community).open().filter(type=Listing.TYPE_WISH, project=None, kind__in=Listing.THING_KINDS)
        .order_by("-updated_at")
    )


@login_required
@require_POST
def volunteer_request(request, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    owner = community.owner
    if not owner:
        messages.error(request, _("This community has no contact person."))
        return redirect(community.get_absolute_url())

    import datetime
    from django.utils import timezone
    from gift_economy.matches.models import Match, VolunteerDetails
    from gift_economy.matches.emails import notify_match_created

    volunteer_mode       = request.POST.get("volunteer_mode", "")
    practice_skills      = request.POST.get("practice_skills", "").strip()
    practice_skill_level = request.POST.get("practice_skill_level", "").strip()
    sender_skills        = request.POST.get("sender_skills", "").strip()
    msg_body             = request.POST.get("body", "").strip()

    def _parse_dt(val):
        if not val:
            return None
        try:
            dt = datetime.datetime.fromisoformat(val)
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except ValueError:
            return None

    stay_from = _parse_dt(request.POST.get("stay_from", ""))
    stay_to   = _parse_dt(request.POST.get("stay_to", ""))

    vr = Match(
        from_user = request.user,
        recipient = community.get_match_owner(),
        message   = msg_body,
    )
    vr.target = community
    vr.save()
    VolunteerDetails.objects.create(
        match                 = vr,
        volunteer_mode        = volunteer_mode,
        practice_skills       = practice_skills,
        practice_skill_level  = practice_skill_level,
        sender_skills         = sender_skills,
        stay_from             = stay_from,
        stay_to               = stay_to,
    )

    # Needs of the community's projects and its wishes they bring along
    from gift_economy.gifts import units
    from gift_economy.matches.models import Contribution
    needs = Listing.objects.of(community).current().filter(
        type=Listing.TYPE_WISH, pk__in=request.POST.getlist("need"), project__isnull=False,
    ).prefetch_related("contributions__match")
    wishes = [listing for listing in _community_wishes(community) if listing.pk in request.POST.getlist("listing")]
    Contribution.objects.bulk_create([
        # A volunteer counts as one person towards a need for people
        Contribution(listing=need, match=vr, quantity=1 if need.quantity and need.unit == units.PEOPLE else None)
        for need in needs if not need.is_done
    ] + [Contribution(listing=listing, match=vr) for listing in wishes])

    notify_match_created(vr, http_request=request)

    messages.success(request, str(_("Your request has been sent to %(community)s!") % {"community": community.name}))

    offer_list = [s.strip() for s in sender_skills.split(",") if s.strip()]
    practice_list = [s.strip() for s in practice_skills.split(",") if s.strip()]
    # Answering a community's wish, the practice skills are ones the volunteer helps with
    if volunteer_mode == "wish":
        offer_list, wish_list = offer_list + practice_list, []
    else:
        wish_list = practice_list

    if offer_list or wish_list:
        mine = Listing.objects.of(request.user).filter(kind=Listing.KIND_SKILL).select_related("skill")

        def slugs(listings):
            # A skill's stored slug can differ from the one its name resolves to
            return {slug for l in listings if l.skill for slug in (l.skill.slug, skill_slug_for_name(l.skill.name))}

        existing_offers = slugs(mine.filter(type=Listing.TYPE_OFFER))
        existing_wishes = slugs(mine.filter(type=Listing.TYPE_WISH))
        offer_list = [s for s in offer_list if skill_slug_for_name(s) not in existing_offers]
        wish_list  = [s for s in wish_list  if skill_slug_for_name(s) not in existing_wishes]

    if request.headers.get("HX-Request") and (offer_list or wish_list):
        return render(request, "communities/_volunteer_skill_proposal.html", {
            "community":  community,
            "offer_list": offer_list,
            "wish_list":  wish_list,
            "single_skill": len(offer_list) + len(wish_list) == 1,
            "review_url": _skill_proposal_url(offer_list, wish_list),
        })

    if request.headers.get("HX-Request"):
        return render(request, "_messages.html")
    return redirect(vr.get_absolute_url())


def _skill_proposal_url(offer_list, wish_list):
    """Where to add skills from a volunteer request to the profile.

    One skill goes straight to the add-skill form, prefilled, so a level and
    description can be set; several go to a short page with a level per skill.
    """
    if len(offer_list) + len(wish_list) == 1:
        name, mode = (offer_list[0], "offer") if offer_list else (wish_list[0], "wish")
        skill = Skill.objects.filter(slug=skill_slug_for_name(name)).first()
        return reverse("gifts:create") + "?" + urlencode({
            "skill": skill.get_name() if skill else name,
            "type":  mode,
            "kind":  "skill",
        })
    params = {}
    if offer_list:
        params["offer"] = ",".join(skill_slug_for_name(s) for s in offer_list)
    if wish_list:
        params["wish"] = ",".join(skill_slug_for_name(s) for s in wish_list)
    return reverse("skills:userskill_add_several") + "?" + urlencode(params)


def _sync_community_skill_wishes(community, form):
    wish_val = form.cleaned_data.get('skill_wishes', '') or ''
    sync_skill_listings(community, Listing.TYPE_WISH, [s.strip() for s in wish_val.split(',') if s.strip()])


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

def _search_q(q):
    """Communities whose name, description or place match the search, or one of whose
    current offers and wishes (skills you can learn there, what its projects need) or
    current projects does ("rocket stove" finds the community building one)."""
    from projects.models import Project
    projects = Project.objects.current().filter(Q(title__icontains=q) | Q(description__icontains=q))
    listings = Listing.objects.current().filter(community__isnull=False).filter(
        Q(title__icontains=q) | Q(description__icontains=q) | skill_name_q(q)
    )
    return (
        Q(name__icontains=q)
        | Q(description__icontains=q)
        | Q(location_name__icontains=q)
        | Q(pk__in=listings.values("community_id"))
        | Q(pk__in=projects.values("community_id"))
    )


def _skill_offers():
    """A community's skills you can learn there (also in its current projects), for its card."""
    return Prefetch(
        "listings",
        queryset=Listing.objects.current().filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
        .select_related("skill").order_by("skill__name"),
        to_attr="skill_offers",
    )


def _current_projects():
    """A community's current projects for its list card: dated ones by start, ongoing last."""
    from projects.models import Project
    return Prefetch(
        "projects",
        queryset=Project.objects.current().order_by(F("starts_on").asc(nulls_last=True), "title"),
        to_attr="current_projects",
    )


def _base_qs(request, require_location=True):
    """Return a Community queryset filtered by ?q= search term."""
    qs = Community.objects.filter(location__isnull=False) if require_location else Community.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(_search_q(q))
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
    qs = _base_qs(request).prefetch_related(hero_prefetch, _skill_offers())

    bbox_param = request.GET.get("bbox", "")
    if bbox_param:
        try:
            west, south, east, north = map(float, bbox_param.split(","))
            bbox_poly = Polygon.from_bbox((west, south, east, north))
            bbox_poly.srid = 4326
            qs = qs.annotate(spot=public_location()).filter(spot__within=bbox_poly)
        except (ValueError, TypeError):
            pass  # ignore malformed bbox

    country_param = request.GET.get("country", "").strip()
    if country_param:
        qs = qs.filter(country=country_param)

    features = []
    for c in qs[:500]:  # hard cap per request
        # Somewhere in its cell, unless it's public (users.places)
        _name, point = c.rough_place()
        first_photo = c.hero_photos[0] if c.hero_photos else None
        photo_url = first_photo.image.url if first_photo and first_photo.image else None
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [point.x, point.y],
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
                "skills":      sorted({cs.skill.get_name() for cs in c.skill_offers}),
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def community_list_partial(request):
    """
    HTML partial for the list modal — HTMX swaps into #community-modal-list.

    Supports:
        q         full-text search (name, description, location, skills, current projects)
        country   ISO country code filter (exact, from CountryField)
        type      community type filter (repeatable)
        status    community status filter (repeatable)
        location  lat,lon — when present, annotates with Distance and sorts
                  by proximity. No hard radius cap; results are ordered
                  nearest-first so the user naturally sees close ones first.
        page      page number for infinite scroll (default 1)
    """
    qs = _base_qs(request, require_location=False).prefetch_related(_skill_offers(), "photos", _current_projects())

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
            # To its cell's centre, unless it's public: tells nothing finer (users.places)
            qs = qs.annotate(
                distance=Distance(Cast(public_location(), PointField(geography=True, srid=4326)), user_point)
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
    where type is one of 'name' | 'location' | 'skill' | 'project' | 'text'.
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

    # Description / vision — extract words that start with the query
    q_lower = q.lower()
    for desc, vision in (
        Community.objects
        .filter(Q(description__icontains=q) | Q(vision__icontains=q))
        .exclude(name__icontains=q)
        .values_list("description", "vision")[:5]
    ):
        for word in re.findall(r'\b\w[\w-]*\b', (desc or "") + " " + (vision or "")):
            if word.lower().startswith(q_lower) and word.lower() != q_lower:
                add(word.lower(), "text")

    # Locations (split on comma to surface city/country parts)
    for loc in Community.objects.filter(location_name__icontains=q).values_list("location_name", flat=True)[:10]:
        # Never the street (users.places)
        for part in (town(loc) or "").split(","):
            if q.lower() in part.lower():
                add(part.strip(), "location")
        if len(suggestions) >= 8:
            break

    # Current projects ("Rocket stove")
    from projects.models import Project
    for title in Project.objects.current().filter(title__icontains=q).values_list("title", flat=True)[:5]:
        add(title, "project")

    # Skills attached to a Community
    for skill in Skill.objects.filter(skill_name_q(q, ""), listings__community__isnull=False).distinct()[:5]:
        add(skill.get_name(), "skill")

    return JsonResponse(suggestions[:12], safe=False)
