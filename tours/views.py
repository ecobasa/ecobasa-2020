from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from communities.models import Community
from dashboard_lists import paginate
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import Skill, skill_name_q

from .forms import StopForm, TourForm
from .geo import MAX_TOURS, TourFilters, feature_collection
from .models import Stop, Tour, append_stop, move_stop, remove_stop

_STOPS = ("stops__event__community", "stops__community__photos", "learn_skills")


def _tours():
    return Tour.objects.select_related("organiser").prefetch_related(*_STOPS)


def _tour(slug, user):
    """The tour, if `user` may see it. Who may not gets a 404, so a draft or a personal
    tour doesn't even say it exists."""
    tour = get_object_or_404(_tours(), slug=slug)
    if not tour.can_view(user):
        raise Http404
    return tour


def _editable(slug, user):
    tour = get_object_or_404(Tour.objects.select_related("organiser"), slug=slug)
    if not tour.can_edit(user):
        raise PermissionDenied
    return tour


def _results(request):
    """The tours of the index for the filters in the query string: tours with dates by
    when they start, then tour ideas, the freshest first (`show` keeps to one of them).
    Page links point at the list partial, which the page swaps in."""
    filters = TourFilters(request.GET, request.user)
    tours = list(filters.apply(_tours().listed().current()))
    ideas = sorted((tour for tour in tours if tour.is_idea), key=lambda tour: -tour.updated_at.timestamp())
    dated = sorted((tour for tour in tours if not tour.is_idea), key=lambda tour: tour.starts_on)
    # Near a place: nearest first (dates and freshness keep their order among equals)
    page = paginate(request, filters.by_distance(dated) + filters.by_distance(ideas))
    base = reverse("tours:api-list")

    def url(number):
        query = request.GET.copy()
        query.pop("bbox", None)
        query["page"] = number
        return f"{base}?{query.urlencode()}"

    page.previous_url = url(page.previous_page_number()) if page.has_previous() else None
    page.next_url = url(page.next_page_number()) if page.has_next() else None
    return {"tours": page.object_list, "page": page, "filters": filters}


def tour_list(request):
    """Tours on a map, the list in a modal, with a search and filters."""
    own = []
    if request.user.is_authenticated:
        # One's own drafts and personal tours are in no list: they are found here
        own = list(
            _tours().filter(organiser=request.user, archived_at=None)
            .filter(Q(published_at=None) | Q(listed=False))
        )
    return render(request, "tours/tour_list.html", {
        "filters": TourFilters(request.GET), "own": own, "mode_choices": Tour.MODE_CHOICES,
    })


def api_list(request):
    """The list beside the map, for htmx."""
    return render(request, "tours/_results.html", _results(request))


def api_routes(request):
    """GeoJSON of the routes and stops of the listed, current tours in the map's visible
    area (bbox), with the filters of the index. At most MAX_TOURS tours, nearest the
    present first. Places only as everyone sees them."""
    filters = TourFilters(request.GET, request.user)
    tours = filters.in_view(filters.apply(_tours().listed().current()))
    tours.sort(key=lambda tour: (tour.starts_on is None, tour.starts_on or timezone.localdate()))
    return JsonResponse(feature_collection(tours[:MAX_TOURS], request.user))


def _travellers(tour):
    """Who travels: the organiser, so far (the travellers who join come with joining a tour)."""
    return [tour.organiser] if tour.organiser else []


def _skills(people):
    """The skills the travellers bring along, each skill once with who has it, in one
    list: (listing, people), the listing being one of them to link to."""
    offers = (
        Listing.objects.open().filter(owner__in=people, community=None, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
        .exclude(available=False).select_related("owner", "skill")
    )
    holders = {}
    for offer in offers:
        holders.setdefault(offer.skill_id, []).append(offer)
    skills = [(found[0], [offer.owner for offer in found]) for found in holders.values()]
    return sorted(skills, key=lambda pair: pair[0].display_title)


def tour_detail(request, slug):
    tour = _tour(slug, request.user)
    can_edit = tour.can_edit(request.user)
    if tour.archived_at and not can_edit:
        messages.info(request, _("This tour has been archived."))
    # Who travels, and what they can, only for people logged in (as a person's profile)
    travellers = _travellers(tour) if request.user.is_authenticated else []
    return render(request, "tours/tour_detail.html", {
        "tour": tour,
        "can_edit": can_edit,
        "travellers": travellers,
        "skills": _skills(travellers),
        "route": _route(tour),
        "geojson": feature_collection([tour], request.user),
    })


def _route(tour):
    """The stops in order, each with the place everyone may see and the leg after it."""
    stops = tour.ordered_stops()
    legs = tour.legs(stops)
    route = []
    for index, stop in enumerate(stops):
        name, _point = stop.public_place()
        leg = legs[index] if index < len(legs) else None
        mode = stop.onward_mode or tour.travel_mode
        route.append({
            "stop": stop,
            "number": index + 1,
            "place": name,
            "leg": leg,
            "leg_mode": dict(Tour.MODE_CHOICES)[mode] if leg else None,
            "leg_icon": Tour.MODE_ICONS.get(mode) if leg else None,
        })
    return route


def _save_tour(request, tour, template, context):
    form = TourForm(request.POST or None, request.FILES or None, instance=tour)
    if request.method == "POST" and form.is_valid():
        is_new = tour.pk is None
        with transaction.atomic():
            tour = form.save(commit=False)
            if is_new:
                tour.organiser = request.user
            tour.touch(save=False)
            tour.save()
            form.save_learn_skills(tour)
        if is_new:
            messages.success(request, _("Your tour is saved as a draft. Now add its stops."))
            return redirect(tour.url("plan"))
        messages.success(request, _("The tour has been saved."))
        return redirect(tour.get_absolute_url())
    return render(request, template, {**context, "form": form})


@login_required
def create(request):
    return _save_tour(request, Tour(), "tours/tour_form.html", {})


@login_required
def edit(request, slug):
    tour = _editable(slug, request.user)
    return _save_tour(request, tour, "tours/tour_form.html", {"tour": tour})


@login_required
def plan(request, slug):
    """The route: the stops in order, moving them, and adding one."""
    tour = _editable(slug, request.user)
    form = StopForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stop = form.save(commit=False)
        stop.tour = tour
        with transaction.atomic():
            append_stop(stop)
            tour.touch()
        messages.success(request, _("The stop has been added."))
        return redirect(tour.url("plan"))
    tour = _tours().get(pk=tour.pk)
    return render(request, "tours/plan.html", {
        "tour": tour, "route": _route(tour), "form": form, "can_edit": True,
    })


def _stop(tour, pk):
    return get_object_or_404(Stop.objects.select_related("tour", "event", "community"), tour=tour, pk=pk)


@login_required
def stop_edit(request, slug, pk):
    tour = _editable(slug, request.user)
    stop = _stop(tour, pk)
    form = StopForm(request.POST or None, instance=stop)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            tour.rebuild_route()
            tour.touch()
        messages.success(request, _("The stop has been saved."))
        return redirect(tour.url("plan"))
    return render(request, "tours/stop_form.html", {"tour": tour, "stop": stop, "form": form})


@login_required
@require_POST
def stop_move(request, slug, pk, direction):
    tour = _editable(slug, request.user)
    move_stop(_stop(tour, pk), -1 if direction == "up" else 1)
    tour.touch()
    return redirect(tour.url("plan"))


@login_required
@require_POST
def stop_delete(request, slug, pk):
    tour = _editable(slug, request.user)
    remove_stop(_stop(tour, pk))
    tour.touch()
    messages.success(request, _("The stop has been removed."))
    return redirect(tour.url("plan"))


@login_required
@require_POST
def publish(request, slug):
    tour = _editable(slug, request.user)
    if not tour.is_published:
        tour.published_at = timezone.now()
        tour.save(update_fields=["published_at"])
        tour.touch()
        if tour.listed:
            messages.success(request, _("Your tour is published. Others find it in the list of tours."))
        else:
            messages.success(request, _("Your tour is published. It is not in the list, as you chose."))
    return redirect(tour.get_absolute_url())


@login_required
@require_POST
def archive(request, slug):
    tour = _editable(slug, request.user)
    tour.archived_at = timezone.now()
    tour.save(update_fields=["archived_at"])
    messages.success(request, _("The tour has been archived."))
    return redirect("tours:list")


@login_required
@require_POST
def confirm(request, slug):
    """An organiser says the tour is still current (also brings back an archived one
    that isn't over)."""
    tour = _editable(slug, request.user)
    if tour.is_over:
        messages.error(request, _("This tour is over. Change the days of its stops to bring it back."))
        return redirect(tour.url("plan"))
    tour.touch()
    messages.success(request, _("Thanks, the tour is marked as current."))
    return redirect(tour.get_absolute_url())


@login_required
def api_hosts(request):
    """Communities whose name or place matches `q`, each with its current events, for
    choosing a stop. Places only as everyone sees them."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    communities = list(Community.objects.filter(Q(name__icontains=q) | Q(location_name__icontains=q)).order_by("name")[:8])
    events = {}
    for event in Event.objects.filter(community__in=communities).current().order_by("starts_on", "title"):
        events.setdefault(event.community_id, []).append({
            "id": event.pk, "title": event.title, "kind": str(event.kind_label),
            "dates": render_to_string("events/_event_dates.html", {"event": event}).strip(),
        })
    return JsonResponse({"results": [
        {
            "id": community.pk, "name": community.name, "place": community.rough_place()[0] or "",
            "icon": community.get_type_icon(), "events": events.get(community.pk, []),
        }
        for community in communities
    ]})


def api_suggest(request):
    """Suggestions for the search, from the listed current tours only: their titles, the
    skills they want to learn, and their stops (communities, events, other places)."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    tours = Tour.objects.listed().current()
    suggestions, seen = [], set()

    def add(value, kind):
        if value and value.lower() not in seen and len(suggestions) < 10:
            seen.add(value.lower())
            suggestions.append({"value": value, "type": kind})

    for title in tours.filter(title__icontains=q).values_list("title", flat=True)[:4]:
        add(title, "name")
    for skill in Skill.objects.filter(skill_name_q(q, ""), tours__in=tours).distinct()[:4]:
        add(skill.get_name(), "skill")
    stops = Stop.objects.filter(tour__in=tours)
    for title in stops.filter(event__title__icontains=q).values_list("event__title", flat=True).distinct()[:3]:
        add(title, "event")
    for name in stops.filter(community__name__icontains=q).values_list("community__name", flat=True).distinct()[:3]:
        add(name, "location")
    for name in stops.filter(name__icontains=q).values_list("name", flat=True).distinct()[:3]:
        add(name, "location")
    return JsonResponse(suggestions, safe=False)

