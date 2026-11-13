from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import prefetch_related_objects, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django_countries import countries as all_countries

from communities.models import Community
from dashboard_lists import paginate
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.gifts.skills.models import Skill, skill_name_q

from gift_economy.matches.emails import notify_match_created, notify_match_message, notify_match_response
from gift_economy.matches.models import Contribution, Match, MatchMessage

from . import matching
from .forms import HostForm, JoinForm, StopForm, TourForm, TourNeedFormSet, VehicleFormSet
from .geo import MAX_TOURS, TourFilters, feature_collection
from .models import Stop, Tour, Traveller, append_stop, move_stop, remove_stop

_STOPS = ("stops__event__community", "stops__community__photos", "learn_skills", "vehicles__drivers")


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
        "countries": _countries(),
    })


def _countries():
    """The countries the listed, current tours travel through, by name: (code, name)."""
    codes = set()
    for countries in Tour.objects.listed().current().values_list("countries", flat=True):
        # Stored as "DE,NL,FR"
        codes.update(code for code in (countries or "").split(",") if code)
    return sorted(((code, all_countries.name(code)) for code in codes if all_countries.name(code)), key=lambda pair: pair[1])


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


def _join_state(tour, user):
    """What the join button says: "login", "on" (travels along; "organiser" if one),
    "asked" (an open request, with `match`), "full", "ask", or "" where the tour
    doesn't look for travellers."""
    if not (tour.open_to_join and tour.is_published and tour.is_current):
        if user.is_authenticated and tour.is_organiser(user):
            return {"state": "organiser"}
        return {"state": ""}
    if not user.is_authenticated:
        return {"state": "login"}
    if tour.is_organiser(user):
        return {"state": "organiser"}
    own = _own_request(tour, user)
    if own is not None:
        if own.is_counted:
            return {"state": "on", "traveller": own}
        return {"state": "asked", "traveller": own, "match": own.match}
    free = tour.free_places()
    if all(places is not None and places <= 0 for places in free):
        return {"state": "full"}
    return {"state": "ask"}


def _own_request(tour, user):
    """The user's traveller row on the tour that is still on: added, accepted or asked."""
    for traveller in tour.travellers.filter(user=user).select_related("match"):
        if traveller.match_id is None or not traveller.match.is_closed:
            return traveller
    return None


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
    counted = tour.counted_travellers()
    travellers = counted if request.user.is_authenticated else []
    stops = tour.ordered_stops()
    for traveller in travellers:
        traveller.stretch = "" if traveller.whole_route else _stretch_text(traveller)
    # The communities they are ambassador of, shown with them
    prefetch_related_objects([traveller.user for traveller in travellers], "communities")
    team = tour.team_skill_ids()
    needs = [(need, matching.role(need, team)) for need in tour.needs()]
    return render(request, "tours/tour_detail.html", {
        "needs": needs,
        "vehicles": tour.vehicles.all(),
        "tour": tour,
        "can_edit": can_edit,
        "travellers": travellers,
        # Logged out, one sees how many travel, not who
        "traveller_count": sum(t.people for t in counted),
        "stops": stops,
        "join": _join_state(tour, request.user),
        "skills": _skills([traveller.user for traveller in travellers]),
        "route": _route(tour),
        "geojson": feature_collection([tour], request.user),
    })


def _route(tour):
    """The stops in order, each with the place everyone may see and the leg after it
    (with its free places, on a tour that looks for travellers and has a limit)."""
    from .visits import clashes

    stops = tour.ordered_stops()
    legs = tour.legs(stops)
    free = tour.free_places(stops=stops) if tour.open_to_join else [None] * len(legs)
    clashing = clashes(stops)
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
            "free": max(free[index], 0) if leg and free[index] is not None else None,
            # Its days overlap the stop before (other days agreed with a host, say)
            "clash": index in clashing,
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


def _learnable(tour):
    """What one can learn at the tour's stops and doesn't want to learn yet: an event's
    skills to learn, a community's skill offers (as on its page, also its current
    events'). [(skill, [stop labels])], by name."""
    stops = list(tour.ordered_stops())
    events = {stop.event_id for stop in stops if stop.event_id}
    communities = {stop.community_id for stop in stops if stop.community_id and not stop.event_id}
    offers = (
        Listing.objects.current()
        .filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill__isnull=False)
        .filter(Q(event__in=events) | Q(community__in=communities))
        .exclude(skill__in=tour.learn_skills.all())
        .select_related("skill")
    )
    where = {}
    for offer in offers:
        for stop in stops:
            here = stop.event_id == offer.event_id if stop.event_id else (stop.community_id == offer.community_id)
            if here:
                labels = where.setdefault(offer.skill, [])
                if stop.label not in labels:
                    labels.append(stop.label)
    return sorted(where.items(), key=lambda pair: pair[0].get_name().lower())


@login_required
@require_POST
def learn_add(request, slug):
    """Add skills one can learn at the stops to what the tour wants to learn."""
    tour = _editable(slug, request.user)
    learnable = {skill.pk: skill for skill, _labels in _learnable(tour)}
    # One skill (its button), or all of them ("Add all")
    ids = request.POST.getlist("all") if request.GET.get("all") else request.POST.getlist("skill")
    chosen = [learnable[pk] for pk in map(int, filter(str.isdigit, ids)) if pk in learnable]
    if chosen:
        tour.learn_skills.add(*chosen)
        tour.touch()
        messages.success(request, _("Added to what you want to learn: %(skills)s") % {
            "skills": ", ".join(skill.get_name() for skill in chosen),
        })
    return redirect(tour.url("plan") + "#learn")


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
        "tour": tour, "route": _route(tour), "form": form, "can_edit": True, "learnable": _learnable(tour),
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



# ── Joining ─────────────────────────────────────────────────────────

@login_required
def join(request, slug):
    """Ask to join a tour for the whole route or part of it: a match with the tour as
    target (answered by its organisers) and the traveller it would make. While it is
    open, the same page changes the stretch and the number of people."""
    tour = _tour(slug, request.user)
    if tour.is_organiser(request.user):
        return redirect(tour.get_absolute_url())
    own = _own_request(tour, request.user)
    if own is not None and own.is_counted:
        messages.info(request, _("You are on this tour already."))
        return redirect(tour.get_absolute_url())
    if own is None and not (tour.open_to_join and tour.is_published and tour.is_current and tour.organiser):
        messages.error(request, _("This tour doesn't look for travellers."))
        return redirect(tour.get_absolute_url())

    form = JoinForm(
        tour, request.POST or None, instance=own or Traveller(tour=tour, user=request.user), with_message=own is None,
        preselected=request.GET.getlist("need"),
    )
    if request.method == "POST" and form.is_valid():
        if own is None:
            with transaction.atomic():
                # No meeting place to agree on: the stretch says where (_match_summary.html)
                match = Match(
                    from_user=request.user, recipient=tour.get_match_owner(), message=form.cleaned_data["message"],
                    location_type="",
                )
                match.target = tour
                match.save()
                traveller = form.save(commit=False)
                traveller.match = match
                traveller.save()
                _cover(match, form.chosen_needs())
            notify_match_created(match, http_request=request)
            messages.success(request, _("Your join request has been sent to the organisers."))
        else:
            with transaction.atomic():
                traveller = form.save()
                match = traveller.match
                _cover(match, form.chosen_needs())
            body = _("Changed the request: %(summary)s") % {"summary": tour.get_match_summary(match)}
            MatchMessage.objects.create(match=match, sender=request.user, body=body)
            notify_match_message(match, sender=request.user, message=body, http_request=request)
            messages.success(request, _("Your join request has been changed."))
        return redirect(match.get_absolute_url())

    free = tour.free_places()
    return render(request, "tours/join.html", {
        "tour": tour, "form": form, "own": own,
        "free": free if any(places is not None for places in free) else None,
        "stops": tour.ordered_stops(),
    })


def _cover(match, chosen):
    """The tour's needs a join request covers (Contribution), as chosen on the join page."""
    match.contributions.exclude(listing__in=[need for need, _quantity in chosen]).delete()
    for need, quantity in chosen:
        Contribution.objects.update_or_create(match=match, listing=need, defaults={"quantity": quantity})


def _stretch_text(traveller):
    start, end = traveller.ends()
    if traveller.whole_route or not (start and end):
        return str(_("the whole route"))
    return f"{start.label} → {end.label}"


@login_required
@require_POST
def leave(request, slug):
    """A traveller leaves the tour, with a few words to the organisers. An organiser
    can't: someone else has to take over first."""
    tour = _tour(slug, request.user)
    own = _own_request(tour, request.user)
    if own is None or not own.is_counted:
        return redirect(tour.get_absolute_url())
    if own.is_organiser or tour.organiser_id == request.user.pk:
        messages.error(request, _("As an organiser you can't leave the tour yet."))
        return redirect(tour.get_absolute_url())
    body = request.POST.get("body", "").strip()
    if not body:
        messages.error(request, _("Please write a few words why, the others were counting on you."))
        return redirect(f"{tour.get_absolute_url()}#join")
    _end(own, request, Match.STATUS_WITHDRAWN, body)
    messages.success(request, _("You have left the tour."))
    return redirect(tour.get_absolute_url())


@login_required
@require_POST
def remove(request, slug, pk):
    """An organiser takes someone off the tour, always with a few words to them."""
    tour = _editable(slug, request.user)
    traveller = get_object_or_404(tour.travellers.select_related("match", "user"), pk=pk)
    if traveller.is_organiser or traveller.user_id == tour.organiser_id:
        raise PermissionDenied
    body = request.POST.get("body", "").strip()
    if not body:
        messages.error(request, _("Please write a few words to them why."))
        return redirect(f"{tour.get_absolute_url()}#travellers")
    _end(traveller, request, Match.STATUS_DECLINED, body)
    messages.success(request, _("%(name)s is no longer on the tour.") % {"name": traveller.user.name or traveller.user.email})
    return redirect(f"{tour.get_absolute_url()}#travellers")


def _end(traveller, request, status, body):
    """Take a traveller off the tour: their join request is withdrawn (they left) or
    declined (an organiser took them off), with the words to the other side. Someone
    added without a request is just removed."""
    match = traveller.match
    if match is None:
        traveller.delete()
        return
    with transaction.atomic():
        MatchMessage.objects.create(match=match, sender=request.user, body=body, status_to=status)
        match.status = status
        match.responded_at = timezone.now()
        match.save()
    notify_match_response(match, actor=request.user, http_request=request, message=body)


@login_required
def mine(request):
    """The tours one organises or travels on, and one's open join requests."""
    rows = []
    seen = set()
    for traveller in (
        Traveller.objects.filter(user=request.user)
        .select_related("tour", "match", "from_stop", "to_stop")
        .prefetch_related("tour__stops__event__community", "tour__stops__community")
        .order_by("-tour__updated_at")
    ):
        if traveller.tour_id in seen or (traveller.match_id and traveller.match.is_closed):
            continue
        seen.add(traveller.tour_id)
        rows.append({"tour": traveller.tour, "traveller": traveller, "stretch": _stretch_text(traveller)})
    page = paginate(request, rows)
    return render(request, "tours/mine.html", {"page": page})


@login_required
def ask_host(request, slug, pk):
    """"Ask to host us" on a stop with a host: the days and
    the group come from the tour, the organisers tick what they help with and write a few
    lines. At an event where people just come, the tour only says it is coming."""
    from .visits import ask_host as send

    tour = _editable(slug, request.user)
    stop = _stop(tour, pk)
    if not stop.community_id or not stop.can_ask_host or stop.host.get_match_owner() is None:
        messages.info(request, _("This stop can't be asked to host you."))
        return redirect(tour.get_absolute_url())
    group = stop.group()
    people = max(stop.group_people(group), 1)
    form = HostForm(stop, people, request.POST or None, open_event=stop.joins_open_event)
    if request.method == "POST" and form.is_valid():
        match = send(
            stop, request.user, message=form.cleaned_data["message"],
            stay_from=form.cleaned_data["stay_from"], stay_to=form.cleaned_data["stay_to"],
            contributions=form.chosen_needs(), practice_skills=form.chosen_skills(), http_request=request,
        )
        if stop.joins_open_event:
            messages.success(request, _("The tour is on the event's list."))
            return redirect(tour.get_absolute_url())
        messages.success(request, _("Your request has been sent to %(community)s!") % {"community": stop.community.name})
        return redirect(match.get_absolute_url())
    return render(request, "tours/ask_host.html", {
        "tour": tour, "stop": stop, "form": form, "group": group, "people": people,
    })


# ── Vehicles and what the tour still looks for ──────────────────────

@login_required
def needs(request, slug):
    """The tour's vehicles and what it still looks for, and the skills the hosts on
    the route look for that nobody on the tour has, each a click to add."""
    tour = _editable(slug, request.user)
    vehicles = VehicleFormSet(request.POST or None, request.FILES or None, instance=tour, prefix="vehicles")
    need_rows = TourNeedFormSet(request.POST or None, instance=tour, prefix="needs")
    if request.method == "POST" and vehicles.is_valid() and need_rows.is_valid():
        with transaction.atomic():
            vehicles.save()
            need_rows.save(commit=False)
            for need in need_rows.deleted_objects:
                need.delete()
            # Keep the needs in the order they were entered
            kept = [f for f in need_rows.forms if f.has_changed() or f.instance.pk]
            for order, need_form in enumerate(f for f in kept if f not in need_rows.deleted_forms):
                need = need_form.save(commit=False)
                need.tour = tour
                need.order = order
                need.save()
                need_form.save_category(need)
            tour.touch()
        messages.success(request, _("Saved."))
        return redirect(tour.url("needs"))
    return render(request, "tours/needs.html", {
        "tour": tour, "vehicles": vehicles, "formset": need_rows, "gaps": matching.gaps(tour),
    })


@login_required
@require_POST
def needs_add(request, slug):
    """Add skills the hosts on the route look for to what the tour looks for."""
    tour = _editable(slug, request.user)
    gaps = {skill.pk: skill for skill, _labels in matching.gaps(tour)}
    ids = request.POST.getlist("all") if request.GET.get("all") else request.POST.getlist("skill")
    chosen = [gaps[pk] for pk in map(int, filter(str.isdigit, ids)) if pk in gaps]
    for skill in chosen:
        matching.add_need(tour, skill)
    if chosen:
        tour.touch()
        messages.success(request, _("Added to what you look for: %(skills)s") % {
            "skills": ", ".join(skill.get_name() for skill in chosen),
        })
    return redirect(tour.url("needs") + "#gaps")
