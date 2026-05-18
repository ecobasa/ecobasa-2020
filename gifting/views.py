import json
import urllib.request
import urllib.parse
from datetime import datetime as _dt

from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.mail import send_mail
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Polygon
from django.views.decorators.http import require_GET
from django.core.cache import cache

from .forms import AdForm, AdRequestForm, AdRequestMessageForm
from .filters import AdFilter
from .models import Ad, AdRequest, AdRequestMessage
from communities.models import Community
from users.models import User
from skills.models import UserSkill, CommunitySkill


def _notify_ad_request(ad_request):
    from notifications.models import Notification
    ad = ad_request.ad
    recipient = ad.owner
    if recipient is None:
        return
    link = ad_request.get_absolute_url()
    actor_name = ad_request.from_user.name or ad_request.from_user.email
    if ad.type == "offer":
        verb = _("%(actor)s requested your offer: %(title)s") % {"actor": actor_name, "title": ad.title}
        tag = "gift_request"
        subject_prefix = "Gift request"
        body_action = "requested your offer"
    else:
        verb = _("%(actor)s wants to fulfill your wish: %(title)s") % {"actor": actor_name, "title": ad.title}
        tag = "wish_request"
        subject_prefix = "Wish fulfillment"
        body_action = "offered to fulfill your wish"
    Notification.objects.create(
        recipient=recipient, actor=ad_request.from_user,
        verb=str(verb), link=link, tag=tag,
    )
    body = f"{actor_name} has {body_action} for '{ad.title}'.\n\nMessage:\n{ad_request.message}\n"
    if ad_request.proposed_date:
        body += f"\nProposed date: {ad_request.proposed_date}"
    body += f"\n\nView it here: https://ecobasa.org{link}"
    try:
        send_mail(
            subject=f"[ecobasa] {subject_prefix}: {ad.title}",
            message=body, from_email="noreply@ecobasa.org",
            recipient_list=[recipient.email], fail_silently=True,
        )
    except Exception:
        pass


def _notify_ad_response(ad_request, actor):
    from notifications.models import Notification
    ad = ad_request.ad
    owner = ad.owner
    recipient = ad_request.from_user if actor == owner else owner
    if recipient is None:
        return
    tag_map = {
        AdRequest.STATUS_ACCEPTED: "gift_accepted",
        AdRequest.STATUS_DECLINED: "gift_declined",
        AdRequest.STATUS_COUNTER:  "gift_counter",
    }
    tag = tag_map.get(ad_request.status, "")
    actor_name = actor.name or actor.email
    status_label = ad_request.get_status_display()
    verb = _("%(actor)s %(status)s your request: %(title)s") % {
        "actor": actor_name, "status": status_label.lower(), "title": ad.title
    }
    link = ad_request.get_absolute_url()
    Notification.objects.create(
        recipient=recipient, actor=actor,
        verb=str(verb), link=link, tag=tag,
    )
    body = f"{actor_name} has {status_label.lower()} the request for '{ad.title}'.\n"
    body += f"\n\nView it here: https://ecobasa.org{link}"
    try:
        send_mail(
            subject=f"[ecobasa] Ad request {status_label.lower()}: {ad.title}",
            message=body, from_email="noreply@ecobasa.org",
            recipient_list=[recipient.email], fail_silently=True,
        )
    except Exception:
        pass


def search(request):
    """Show all ads with filter ability"""
    f = AdFilter(request.GET, queryset=Ad.objects.none(), request=request)

    return render(request, "gifting/search.html", {"f": f})


def detail(request, pk):
    """Show details for an Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    context = {"ad": ad}

    if request.user.is_authenticated and request.user != ad.owner:
        if request.method == "POST":
            form = AdRequestForm(request.POST)
            if form.is_valid():
                ar = form.save(commit=False)
                ar.from_user = request.user
                ar.ad = ad
                ar.save()
                _notify_ad_request(ar)
                messages.success(request, _("Your request has been sent."))
                return redirect(ar.get_absolute_url())
        else:
            form = AdRequestForm()
        context["form"] = form

    is_owner = request.user.is_authenticated and request.user == ad.owner
    context["is_owner"] = is_owner
    if is_owner:
        context["incoming_requests"] = list(ad.requests.select_related("from_user").order_by("-created_at")[:20])

    return render(request, "gifting/ad_detail.html", context)


@login_required
def adrequest_detail(request, pk):
    ar = get_object_or_404(AdRequest, pk=pk)
    owner = ar.ad.owner

    if request.user != ar.from_user and request.user != owner:
        raise Http404

    is_owner = request.user == owner
    is_requester = request.user == ar.from_user

    thread = list(ar.thread.select_related("sender").all())
    latest_status_msg = None
    latest_counter_msg = None
    for msg in reversed(thread):
        if msg.status_to and latest_status_msg is None:
            latest_status_msg = msg
        if msg.status_to == AdRequest.STATUS_COUNTER and latest_counter_msg is None:
            latest_counter_msg = msg
        if latest_status_msg and latest_counter_msg:
            break

    counter_by_owner = (
        ar.status == AdRequest.STATUS_COUNTER
        and latest_status_msg is not None
        and latest_status_msg.sender_id == owner.pk
    )
    owner_can_decide = is_owner and not counter_by_owner
    requester_can_decide = is_requester and counter_by_owner

    if request.method == "POST":
        action = request.POST.get("action", "message")

        if action == "message":
            body = request.POST.get("body", "").strip()
            if body:
                AdRequestMessage.objects.create(request=ar, sender=request.user, body=body)
            return redirect(ar.get_absolute_url())

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {"accept": AdRequest.STATUS_ACCEPTED, "decline": AdRequest.STATUS_DECLINED}[action]
            AdRequestMessage.objects.create(
                request=ar, sender=request.user,
                body=request.POST.get("body", "").strip(), status_to=new_status,
            )
            ar.status = new_status
            ar.responded_at = timezone.now()
            ar.save()
            _notify_ad_response(ar, actor=request.user)
            messages.success(request, _("Response sent."))
            return redirect(ar.get_absolute_url())

        if action == "counter" and is_owner:
            msg = AdRequestMessage(
                request=ar, sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=AdRequest.STATUS_COUNTER,
            )
            msg.counter_location_type = request.POST.get("counter_location_type", "")
            msg.counter_location = request.POST.get("counter_location", "")
            try:
                msg.counter_lat = float(request.POST.get("counter_lat") or "")
            except (ValueError, TypeError):
                msg.counter_lat = None
            try:
                msg.counter_lon = float(request.POST.get("counter_lon") or "")
            except (ValueError, TypeError):
                msg.counter_lon = None
            raw_dt = request.POST.get("counter_date", "")
            try:
                msg.counter_date = _dt.fromisoformat(raw_dt) if raw_dt else None
            except ValueError:
                msg.counter_date = None
            msg.save()
            ar.status = AdRequest.STATUS_COUNTER
            ar.responded_at = timezone.now()
            ar.save()
            _notify_ad_response(ar, actor=request.user)
            messages.success(request, _("Counter-proposal sent."))
            return redirect(ar.get_absolute_url())

    return render(request, "gifting/adrequest_detail.html", {
        "ar":                   ar,
        "owner":                owner,
        "is_owner":             is_owner,
        "is_requester":         is_requester,
        "thread":               thread,
        "latest_status_msg":    latest_status_msg,
        "latest_counter_msg":   latest_counter_msg,
        "owner_can_decide":     owner_can_decide,
        "requester_can_decide": requester_can_decide,
        "message_form":         AdRequestMessageForm(),
        "loc_choices":          AdRequest.LOC_CHOICES,
    })


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
    types = request.GET.getlist("type")
    ad_types = [t for t in types if t != "skill"]

    if types and not ad_types:
        return Ad.objects.none()

    base_qs = Ad.objects.filter(location__isnull=False).select_related("owner")

    if "skill" in types:
        data = request.GET.copy()
        data.setlist("type", ad_types)
        f = AdFilter(data, queryset=base_qs, request=request)
    else:
        f = AdFilter(request.GET, queryset=base_qs, request=request)

    return f.qs


def _skill_communities(request):
    types = request.GET.getlist("type")
    if types and "skill" not in types:
        return Community.objects.none()

    qs = Community.objects.filter(
        location__isnull=False,
        community_skills__isnull=False,
    ).prefetch_related("community_skills__skill", "photos").distinct()

    q = request.GET.get("search", "").strip()
    if q:
        qs = qs.filter(
            Q(community_skills__skill__name__icontains=q) | Q(description__icontains=q)
        ).distinct()

    return qs


def _skill_users(request):
    types = request.GET.getlist("type")
    if types and "skill" not in types:
        return User.objects.none()

    qs = User.objects.filter(
        location__isnull=False,
        user_skills__isnull=False,
    ).prefetch_related("user_skills__skill").distinct()

    q = request.GET.get("search", "").strip()
    if q:
        qs = qs.filter(
            Q(user_skills__skill__name__icontains=q) | Q(about__icontains=q)
        ).distinct()

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
        skill_names = [cs.skill.name for cs in community.community_skills.all()]
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

    # ── User skill features ──────────────────────────────────────────
    user_skill_qs = _apply_bbox(_skill_users(request), bbox_param)

    for user in user_skill_qs[:200]:
        skill_names = [us.skill.name for us in user.user_skills.all()]
        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [user.location.x, user.location.y],
            },
            "properties": {
                "source":       "user_skill",
                "title":        ", ".join(skill_names[:3]),
                "description":  user.about or "",
                "image":        user.image.url if user.image else None,
                "type_display": "User Skill",
                "url":          user.get_absolute_url(),
                "user_name":    user.name or user.email,
            },
        })

    return JsonResponse({"type": "FeatureCollection", "features": features})


@require_GET
def gifting_list_partial(request):
    page_num = int(request.GET.get("page", 1))

    ads_queryset = _filtered_ads(request)
    if not request.GET.get('location'):
        ads_queryset = ads_queryset.order_by("-created_at")

    paginator = Paginator(ads_queryset, 20)
    page = paginator.get_page(page_num)

    sc_qs = _skill_communities(request)
    su_qs = _skill_users(request)

    skill_communities = []
    skill_users = []

    if page_num == 1:
        skill_communities = list(sc_qs[:10])
        skill_users = list(su_qs[:10])

    return render(request, "gifting/_gifting_list_partial.html", {
        "ads":               page,
        "skill_communities": skill_communities,
        "skill_users":       skill_users,
        "has_next":          page.has_next(),
        "next_page":         page.next_page_number() if page.has_next() else None,
        "total":             paginator.count + sc_qs.count() + su_qs.count(),
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
def gifting_suggest(request):
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
    for ad in (
        Ad.objects
        .filter(title__icontains=q)
        .values('title', 'type')[:4]
    ):
        add(ad['title'], ad['type'])

    # Owner names — placed early so they aren't cut off by the 8-item limit
    for user in (
        User.objects
        .filter(Q(name__icontains=q) | Q(email__icontains=q), ads__isnull=False)
        .only("name", "email")
        .distinct()[:2]
    ):
        add(user.name or user.email, "owner")

    # Community skill names
    for skill in (
        CommunitySkill.objects
        .filter(skill__name__icontains=q)
        .values_list("skill__name", flat=True)
        .distinct()[:3]
    ):
        add(skill, "skill")

    # User skill names
    for skill in (
        UserSkill.objects
        .filter(skill__name__icontains=q)
        .values_list("skill__name", flat=True)
        .distinct()[:3]
    ):
        add(skill, "skill")

    # Description match — add query itself as a "text" hint (community list pattern)
    if Ad.objects.filter(
        Q(description__icontains=q) | Q(owner__name__icontains=q)
    ).exclude(title__icontains=q).exists():
        add(q, "text")

    return JsonResponse(suggestions[:8], safe=False)
