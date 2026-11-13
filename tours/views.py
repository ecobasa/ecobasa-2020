from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from communities.models import Community
from dashboard_lists import Choice, paginate, query_url
from events.models import Event

from .forms import StopForm, TourForm
from .models import Stop, Tour, append_stop, move_stop, remove_stop

_STOPS = ("stops__event__community", "stops__community", "learn_skills")


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


def tour_list(request):
    """Published tours that are shown in the list, current ones first: tours with dates
    and, on their own tab, tour ideas."""
    tours = list(_tours().listed().current())
    ideas = [tour for tour in tours if tour.is_idea]
    dated = sorted((tour for tour in tours if not tour.is_idea), key=lambda tour: tour.starts_on)
    tab = "ideas" if request.GET.get("tab") == "ideas" else "tours"
    tabs = [
        Choice(_("Tours"), query_url(request, tab=None), tab == "tours", len(dated)),
        Choice(_("Tour ideas"), query_url(request, tab="ideas"), tab == "ideas", len(ideas)),
    ]
    page = paginate(request, ideas if tab == "ideas" else dated)
    own = []
    if request.user.is_authenticated:
        # One's own drafts and personal tours are in no list: they are found here
        own = list(
            _tours().filter(organiser=request.user, archived_at=None)
            .filter(Q(published_at=None) | Q(listed=False))
        )
    return render(request, "tours/tour_list.html", {
        "tours": page.object_list, "page": page, "tabs": tabs, "tab": tab, "own": own,
    })


def tour_detail(request, slug):
    tour = _tour(slug, request.user)
    can_edit = tour.can_edit(request.user)
    if tour.archived_at and not can_edit:
        messages.info(request, _("This tour has been archived."))
    return render(request, "tours/tour_detail.html", {
        "tour": tour,
        "can_edit": can_edit,
        "route": _route(tour),
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
            return redirect(tour.url("stops"))
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
def stops(request, slug):
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
        return redirect(tour.url("stops"))
    tour = _tours().get(pk=tour.pk)
    return render(request, "tours/stops.html", {
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
        return redirect(tour.url("stops"))
    return render(request, "tours/stop_form.html", {"tour": tour, "stop": stop, "form": form})


@login_required
@require_POST
def stop_move(request, slug, pk, direction):
    tour = _editable(slug, request.user)
    move_stop(_stop(tour, pk), -1 if direction == "up" else 1)
    tour.touch()
    return redirect(tour.url("stops"))


@login_required
@require_POST
def stop_delete(request, slug, pk):
    tour = _editable(slug, request.user)
    remove_stop(_stop(tour, pk))
    tour.touch()
    messages.success(request, _("The stop has been removed."))
    return redirect(tour.url("stops"))


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
        return redirect(tour.url("stops"))
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
