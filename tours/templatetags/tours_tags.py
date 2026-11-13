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


@register.inclusion_tag("tours/_tour_visits.html", takes_context=True)
def tour_visits_to(context, host):
    """"Tour visits" (N25) on a community's or event's page: the tours its host agreed to
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
