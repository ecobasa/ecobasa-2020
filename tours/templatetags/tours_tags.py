from django import template

from ..models import Stop, Tour, Traveller

register = template.Library()


@register.inclusion_tag("tours/_profile_tours.html", takes_context=True)
def tours_of(context, person):
    """The tours someone organises or travels on, for their profile: the ones the viewer
    may see, current ones first. Archived tours only on one's own profile."""
    viewer = context["request"].user
    own = viewer.is_authenticated and viewer.pk == person.pk
    travels = (
        Traveller.objects.filter(user=person)
        .select_related("tour__organiser", "match")
        .prefetch_related("tour__stops", "tour__learn_skills")
        .order_by("-tour__updated_at")
    )
    tours, seen = [], set()
    for traveller in travels:
        tour = traveller.tour
        if tour.pk in seen or not traveller.is_counted:
            continue
        if (tour.archived_at and not own) or not tour.can_view(viewer):
            continue
        seen.add(tour.pk)
        tours.append(tour)
    tours.sort(key=lambda tour: not tour.is_current)
    return {"tours": tours, "user": viewer}


@register.inclusion_tag("tours/_invite_to_tours.html", takes_context=True)
def invite_to_tours(context, person):
    """On someone's profile: the viewer's tours they could be invited to (published,
    current, looking for travellers, and they aren't on it or asked yet)."""
    viewer = context["request"].user
    if not viewer.is_authenticated or viewer.pk == person.pk:
        return {"tours": []}
    organised = (
        Tour.objects.published().current().filter(open_to_join=True)
        .filter(pk__in=Traveller.objects.counted().filter(user=viewer, is_organiser=True).values("tour_id"))
        .distinct()
    )
    taken = {
        traveller.tour_id for traveller in Traveller.objects.filter(user=person, tour__in=organised).select_related("match")
        if traveller.match_id is None or not traveller.match.is_closed
    }
    return {"tours": [tour for tour in organised if tour.pk not in taken], "person": person}


@register.inclusion_tag("tours/_tour_visits.html", takes_context=True)
def tour_visits_to(context, host):
    """"Tour visits" on a community's or event's page: the tours its host agreed to
    take (or that come to its open event), not over yet, as the viewer may see them. A
    community lists the visits to its events too."""
    from django.db.models import Q
    from django.utils import timezone

    from gift_economy.matches.models import Match

    viewer = context["request"].user
    at = Q(event=host) if host._meta.model_name == "event" else Q(community=host)
    stops = (
        Stop.objects.filter(at, visit_match__status=Match.STATUS_ACCEPTED, tour__archived_at=None)
        .filter(Q(leave_on=None) | Q(leave_on__gte=timezone.localdate()))
        .select_related("tour", "event", "visit_match__stay_details")
        .order_by("arrive_on", "pk")
    )
    return {
        "stops": [stop for stop in stops if stop.tour.can_view(viewer)],
        "on_event": host._meta.model_name == "event",
    }


@register.inclusion_tag("tours/_need_tour.html", takes_context=True)
def tour_box(context, tour):
    """The tour on the gift page of something it looks for: what it is, who and how many
    travel, and where it goes, so one can tell whether one can help. Places as everyone
    sees them; who organises it only for people logged in, as on the tour's page."""
    viewer = context["request"].user
    stops = tour.ordered_stops()
    counted = tour.counted_travellers()
    free = tour.free_on(stops=stops) if tour.open_to_join else None
    return {
        "tour": tour,
        "stops": [(stop, stop.public_place()[0]) for stop in stops],
        "people": sum(t.people for t in counted),
        "free": free,
        "organiser": tour.organiser if viewer.is_authenticated else None,
    }


@register.simple_tag(takes_context=True)
def tour_geojson(context, tour):
    """The tour's route and stops as GeoJSON for a map, at the places everyone may see."""
    from ..geo import feature_collection

    return feature_collection([tour], context["request"].user)


@register.inclusion_tag("tours/_deliveries_box.html", takes_context=True)
def deliveries_with(context, obj):
    """"Deliveries" on a gift's, community's or event's page: the gifts taken along on
    tours that it gives or receives, as the viewer may see the tours. Not what didn't
    work out or was set aside."""
    from django.db.models import Q

    from ..models import Delivery

    viewer = context["request"].user
    model = obj._meta.model_name
    if model == "listing":
        found = Delivery.objects.touching(obj)
    elif model == "event":
        found = Delivery.objects.filter(Q(offer__event=obj) | Q(wish__event=obj))
    else:
        found = Delivery.objects.filter(Q(offer__community=obj) | Q(wish__community=obj))
    found = (
        found.active().select_related(
            "tour", "offer__owner", "offer__community", "wish__owner", "wish__community", "wish__tour",
            "pickup_stop__community", "pickup_stop__event", "dropoff_stop__community", "dropoff_stop__event",
            "bringer", "pickup_match", "handover_match",
        ).order_by("-created_at")[:20]
    )
    shown = [d for d in found if d.status != Delivery.STATUS_FELL_THROUGH and d.tour.can_view(viewer)]
    return {"deliveries": shown, "user": viewer}


@register.inclusion_tag("tours/_tours_going_there.html", takes_context=True)
def tours_going_there(context, match):
    """On a stay's match page, for the one who stays: the tours that stop there around
    their days and have room, each with the stretch to get there."""
    from ..matching import by_stay, joinable, stays_of

    viewer = context["request"].user
    if not viewer.is_authenticated or viewer.pk != match.from_user_id:
        return {"fits": []}
    stays = stays_of(viewer).filter(pk=match.pk)
    fits = by_stay(viewer, joinable(viewer), stays=stays)
    return {"fits": sorted(fits, key=lambda fit: fit.tour.starts_on or fit.tour.created_at.date())}


@register.inclusion_tag("tours/_go_together.html", takes_context=True)
def go_together(context, event):
    """On an event's page, for who is coming: start a tour there, and how many others
    from near them come in the same days."""
    from gift_economy.matches.matching import distance_km

    from ..matching import around_days, stay_days, stays_of

    viewer = context["request"].user
    if not viewer.is_authenticated or not event.is_current:
        return {}
    own = stays_of(viewer).filter(content_type__model="event", object_id=str(event.pk)).first()
    if own is None:
        return {}
    days = stay_days(own)
    near = set()
    if viewer.location is not None:
        for stay in event.matches.exclude(from_user=viewer).filter(status="accepted").select_related("stay_details", "from_user"):
            home = stay.from_user.location
            if home is not None and distance_km(viewer.location, home) <= (viewer.match_radius or 0) and around_days(stay_days(stay), *days):
                near.add(stay.from_user_id)
    return {"event": event, "others": len(near)}
