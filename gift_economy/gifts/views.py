import json
import re
import urllib.request
import urllib.parse
from collections import Counter

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.db.models import Count, Q
from django.db.models.functions import Cast, Coalesce
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos import Polygon
from django.views.decorators.http import require_GET
from django.core.cache import cache

from .forms import ListingForm
from .filters import ListingFilter
from .models import Listing
from communities.models import Community
from gift_economy.references.models import Reference
from users.models import User
from gift_economy.gifts.skills.models import Skill, skill_name_q
from gift_economy.matches.forms import MatchForm
from gift_economy.matches.models import Contribution, Loan, Match
from gift_economy.matches.emails import notify_match_created
from dashboard_lists import Choice, paginate, query_url


def search(request):
    """Show all listings with filter ability"""
    f = ListingFilter(request.GET, queryset=Listing.objects.none(), request=request)

    return render(request, "gifts/search.html", {"f": f})


def detail(request, pk):
    """An offer or a wish of any kind, with the request form. A project's need is helped
    with through the project's offer form; a community's wish for a skill through its
    volunteer form."""
    listing = get_object_or_404(
        Listing.objects.select_related("owner", "community__owner", "project", "skill", "thing")
        .prefetch_related("categories", "contributions__match__from_user"),
        pk=pk,
    )
    can_edit = listing.can_edit(request.user)
    context = {"listing": listing, "can_edit": can_edit, "is_owner": can_edit}
    help_url = _help_url(listing)
    context["help_url"] = help_url

    manager = listing.manager
    if request.user.is_authenticated and manager is not None and request.user != manager and not help_url:
        form = MatchForm(request.POST or None, loan_of=listing if listing.lend else None)
        if request.method == "POST" and form.is_valid():
            match = form.save(commit=False)
            match.from_user = request.user
            match.recipient = manager
            match.target = listing
            match.save()
            Contribution.objects.create(match=match, listing=listing, quantity=form.cleaned_data.get("quantity"))
            if listing.lend:
                starts_at, ends_at = form.cleaned_data["loan"]
                Loan.objects.create(match=match, starts_at=starts_at, ends_at=ends_at)
            notify_match_created(match, http_request=request)
            messages.success(request, _("Your request has been sent."))
            return redirect(match.get_absolute_url())
        context["form"] = form

    if listing.lends_out:
        context["upcoming_loans"] = listing.upcoming_loans()
    if can_edit:
        context["incoming_requests"] = list(
            Match.objects.filter(contributions__listing=listing).select_related("from_user").distinct().order_by("-created_at")[:20]
        )
    return render(request, "gifts/listing_detail.html", context)


def _help_url(listing):
    """Where to answer what isn't asked for by its own request: help with a project's need
    on the project's offer form, with a community's wish for a skill or learning one of
    its skills on its volunteer form."""
    if listing.is_offer:
        if listing.community_id and listing.skill_id:
            return f"{listing.community.get_absolute_url()}?learn={listing.skill.slug}"
        return ""
    if listing.project_id:
        return f"{reverse('projects:offer_help', args=[listing.project_id])}?need={listing.pk}"
    if listing.community_id and listing.skill_id:
        return f"{listing.community.get_absolute_url()}?help={listing.skill.slug}"
    return ""


@login_required
def mine(request):
    """Your own offers and wishes in the dashboard, things and skills, with how many asked
    about each (and, for skills, how many references they have)."""
    box = "wish" if request.GET.get("box") == "wish" else "offer"
    what = request.GET.get("what", "")
    # Requests and exchanges it is part of
    listings = Listing.objects.of(request.user).select_related("skill").prefetch_related("categories").annotate(
        match_count=Count("contributions", distinct=True),
    ).order_by("-updated_at")
    if what == "skills":
        listings = listings.skills()
    elif what == "things":
        listings = listings.things()
    counts = {key: listings.filter(type=key).count() for key in ("offer", "wish")}
    tabs = [
        Choice(label, query_url(request, box=key, page=None), key == box, counts[key])
        for key, label in (("offer", _("Your offers")), ("wish", _("Your wishes")))
    ]
    whats = [
        Choice(label, query_url(request, what=key or None, page=None), key == what, icon=icon)
        for key, label, icon in (("", _("All"), ""), ("things", _("Things"), "fa-gift"), ("skills", _("Skills"), "fa-graduation-cap"))
    ]
    page = paginate(request, listings.filter(type=box))
    references = Counter(Reference.objects.filter(
        content_type=ContentType.objects.get_for_model(Listing),
        object_id__in=[listing.pk for listing in page.object_list],
    ).values_list("object_id", flat=True))
    for listing in page.object_list:
        listing.reference_count = references[listing.pk]
    return render(request, "gifts/mine.html", {"tabs": tabs, "whats": whats, "what": what, "box": box, "page": page})


def _holder_for(request):
    """Who a new listing is for: a community its ambassador names (?community=<slug>),
    else the person."""
    slug = request.POST.get("community") or request.GET.get("community")
    if not slug:
        return None
    community = get_object_or_404(Community, slug=slug)
    if not (request.user.is_staff or request.user == community.owner):
        raise PermissionDenied
    return community


@login_required
def create(request):
    """A new offer or wish: ?type=offer|wish, ?kind=…, ?skill=<name>, ?lend=1 and
    ?community=<slug> preset it."""
    community = _holder_for(request)
    initial = {
        "type": request.GET.get("type") if request.GET.get("type") in ("offer", "wish") else "offer",
        "kind": request.GET.get("kind") if request.GET.get("kind") in dict(Listing.KIND_CHOICES) else Listing.KIND_OTHER,
        "skill_name": request.GET.get("skill", ""),
        # Vehicles are mostly lent rather than given away
        "lend": request.GET.get("lend") == "1" or request.GET.get("kind") == Listing.KIND_VEHICLE,
        **_holder_place(community or request.user),
    }
    posted = request.method == "POST"
    form = ListingForm(request.POST if posted else None, request.FILES if posted else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        listing = form.save(commit=False)
        if community is not None:
            listing.community = community
        else:
            listing.owner = request.user
        _keep_own_place_only(listing)
        listing.save()
        form.save_m2m()
        messages.success(
            request, _("%(listing_type)s created") % {"listing_type": listing.get_type_display()}
        )
        return redirect(listing.get_absolute_url())
    return render(request, "gifts/listing_form.html", {"form": form, "community": community, **_form_context()})


def _holder_place(holder):
    """The form's place to start from: the person's or the community's, from its profile,
    to keep or move on the map."""
    if holder is None or holder.location is None:
        return {}
    return {"location": holder.location, "location_name": holder.location_name}


def _keep_own_place_only(listing):
    """A place left as the profile's isn't the listing's own: it stays where its person
    or community is, also when they move. One moved on the map is its own."""
    holder = listing.holder
    if listing.location is not None and holder is not None and holder.location is not None and (
        listing.location.equals_exact(holder.location, tolerance=1e-6)
    ):
        listing.location, listing.location_name = None, None


def _form_context():
    """What the listing form's script needs: the kinds named from their vocabulary only."""
    from .things import WHITELISTED_KINDS
    return {"whitelisted_kinds": json.dumps(list(WHITELISTED_KINDS))}


@login_required
def edit(request, pk):
    """Edit an existing Listing"""
    listing = get_object_or_404(Listing, pk=pk)
    if not listing.can_edit(request.user):
        raise PermissionDenied

    posted = request.method == "POST"
    # Without a place of its own, it is where its person or community is: shown on the map
    initial = {} if listing.location else _holder_place(listing.holder)
    form = ListingForm(request.POST if posted else None, request.FILES if posted else None, instance=listing, initial=initial)
    if request.method == "POST" and form.is_valid():
        listing = form.save(commit=False)
        _keep_own_place_only(listing)
        listing.save()
        form.save_m2m()
        messages.success(request, _("changes saved"))
        return redirect(listing.get_absolute_url())
    return render(request, "gifts/listing_form.html", {
        "form": form, "listing": listing, "community": listing.community, **_form_context(),
    })


@login_required
def delete(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    if not listing.can_edit(request.user):
        raise PermissionDenied

    if request.method == "POST":
        back = listing.project.get_absolute_url() if listing.project_id else (
            listing.community.get_absolute_url() if listing.community_id else reverse("gifts:mine")
        )
        listing.delete()
        messages.success(
            request, _("%(listing_type)s deleted") % {"listing_type": listing.get_type_display()}
        )
        return redirect(back)
    return render(request, "gifts/listing_delete_confirm.html", {"listing": listing})


# ── Shared helpers ───────────────────────────────────────────────────

def _with_spot(qs):
    """Each listing with where it is (`spot`): its own place, else its person's or community's."""
    return qs.annotate(spot=Coalesce("location", "owner__location", "community__location"))


def _apply_bbox(qs, bbox_param):
    """Filter listings to those whose place is within the bbox string 'w,s,e,n'."""
    if not bbox_param:
        return qs
    try:
        west, south, east, north = map(float, bbox_param.split(","))
    except (ValueError, TypeError):
        return qs
    poly = Polygon.from_bbox((west, south, east, north))
    poly.srid = 4326
    # As a flat lon/lat box: on geography the box's edges would be great circles, and a
    # box wider than half the world (the map zoomed out) would turn inside out
    return qs.annotate(flat_spot=Cast("spot", GeometryField(srid=4326))).filter(flat_spot__intersects=poly)


def _filtered_listings(request, require_location=True):
    """What the map and list show: current listings, filtered (ListingFilter), each with
    its place. Offers and wishes of things, skills, knowledge and helping hands of people
    and communities, and the needs of current projects."""
    base_qs = _with_spot(Listing.objects.open()).select_related(
        "owner", "community", "project", "skill",
    ).exclude(owner=None, community=None).exclude(type=Listing.TYPE_OFFER, skill__isnull=False, available=False)
    if require_location:
        base_qs = base_qs.filter(spot__isnull=False)
    return ListingFilter(request.GET, queryset=base_qs, request=request).qs


# ── Endpoints ────────────────────────────────────────────────────────

def _public_name(user):
    """Name shown on public map popups; never falls back to the email address."""
    if not user:
        return ""
    return user.name or user.username or ""


def _marker_colour(listing):
    if listing.project_id and listing.is_wish:
        return "#5A5527"  # green: a project's need
    if listing.is_skill:
        return "#80143b"  # purple
    return "#de7a08" if listing.is_wish else "#da6137"


@require_GET
def gifts_markers(request):
    """
    GeoJSON FeatureCollection — one marker per offer or wish (things, skills, knowledge,
    helping hands, project needs) within the current map viewport bounding box, at its
    own place or its person's or community's.

    Query params (all optional):
        bbox        west,south,east,north  (WGS84)
        search      search term
        type        offer | wish | skill | need (repeatable)
        kind        kind filter (repeatable)
        categories  category id filter (repeatable)
        location    lat,lon  → distance-ordered results via ListingFilter
    """
    features = []
    listings = _apply_bbox(_filtered_listings(request), request.GET.get("bbox", "")).prefetch_related("owner__communities")
    for listing in listings[:700]:
        holder = listing.holder
        photo = listing.image.url if listing.image else None
        if photo is None and listing.community_id:
            first = listing.community.photos.first()
            photo = first.image.url if first and first.image else None
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [listing.spot.x, listing.spot.y]},
            "properties": {
                "source":         "listing",
                "title":          listing.display_title,
                "description":    listing.description,
                "image":          photo,
                "listing_type":   listing.type,
                "glyph":          listing.marker_glyph,
                "color":          _marker_colour(listing),
                "kind_icon":      listing.kind_icon if listing.kind != Listing.KIND_OTHER else "",
                "amount":         listing.amount,
                "type_display":   f"{listing.get_type_display()} · {listing.kind_label}" if listing.kind != Listing.KIND_OTHER else listing.get_type_display(),
                "url":            listing.get_absolute_url(),
                "project":        listing.project.title if listing.project_id else "",
                "community_name": listing.community.name if listing.community_id else "",
                "user_name":      "" if listing.community_id else _public_name(holder),
                "member_of":      "" if listing.community_id or not holder else ", ".join(c.name for c in holder.member_communities()),
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def gifts_list_partial(request):
    listings_queryset = _filtered_listings(request, require_location=False).prefetch_related("categories", "community__photos", "owner__communities")
    # Your own (and your communities') are nearest, so they would always come first; the
    # map still shows them
    if request.user.is_authenticated:
        listings_queryset = listings_queryset.exclude(Q(owner=request.user) | Q(community__owner=request.user))
    if not request.GET.get("location"):
        listings_queryset = listings_queryset.order_by("-created_at")

    paginator = Paginator(listings_queryset, 20)
    page = paginator.get_page(request.GET.get("page", 1))

    return render(request, "gifts/_gifts_list_partial.html", {
        "listings":  page,
        "has_next":  page.has_next(),
        "next_page": page.next_page_number() if page.has_next() else None,
        "total":     paginator.count,
        "q":         request.GET.get("search", ""),
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
def things_recognize(request):
    """What a title is recognized as while typing, and the categories that sets:
    ?kind=tool|material|seeds|vehicle&title=… (with &variety=… for seeds)."""
    from .models import Thing
    from .things import WHITELISTED_KINDS, recognize, thing_named
    kind, title = request.GET.get("kind", ""), request.GET.get("title", "").strip()
    if kind in WHITELISTED_KINDS:
        thing_id = thing_named(title, kind)
    else:
        variety = request.GET.get("variety", "").strip()
        thing_id = recognize(f"{title} {variety}" if variety else title, kind) if kind in Listing.CATEGORY_KINDS else None
    thing = Thing.objects.filter(pk=thing_id).select_related("category").first()
    if thing is None:
        return JsonResponse({"thing": None, "categories": []})
    return JsonResponse({
        "thing": thing.get_name(),
        "categories": [str(category) for category in Listing.thing_categories(thing, kind)],
    })


@require_GET
def things_suggest(request):
    """Names from a vocabulary while typing a title: ?kind=seeds|vehicle|…&q=…"""
    from .things import suggest
    lang = (getattr(request, "LANGUAGE_CODE", "") or "en")[:2]
    return JsonResponse({"results": suggest(request.GET.get("q", ""), request.GET.get("kind", ""), lang)})


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

    current = Listing.objects.open()

    # Listing titles (things, and knowledge or helping hands named in words)
    for listing in current.filter(title__icontains=q, skill=None).values("title", "type")[:4]:
        add(listing["title"], listing["type"])

    # Owner names — placed early so they aren't cut off by the 8-item limit
    for user in (
        User.objects
        .filter(Q(name__icontains=q) | Q(email__icontains=q), listings__isnull=False)
        .only("name", "email")
        .distinct()[:2]
    ):
        add(user.name or user.email, "owner")

    # Skills someone offers or wishes for, matched and shown in the active language
    for skill in Skill.objects.filter(skill_name_q(q, ""), listings__in=current).distinct()[:6]:
        add(skill.get_name(), "skill")

    # Description match — extract words that start with the query
    q_lower = q.lower()
    for desc, in current.filter(description__icontains=q).exclude(title__icontains=q).values_list("description")[:8]:
        for word in re.findall(r'\b\w[\w-]*\b', desc or ""):
            if word.lower().startswith(q_lower) and word.lower() != q_lower:
                add(word.lower(), "text")

    return JsonResponse(suggestions[:8], safe=False)
