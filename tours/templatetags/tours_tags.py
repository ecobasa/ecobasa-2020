from django import template

from ..models import Tour, Traveller

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
