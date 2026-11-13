"""What a tour still looks for, found from its route, and why someone who covers a
need would say yes.

The people a need fits are found by the general matching (gift_economy.matches.matching):
a tour's need is a wish whose place is the tour's route."""

from django.db.models import Q

from gift_economy.gifts.models import Listing

# Why a need is worth taking up: shown with it, as the reason someone would say yes
COMPLETES = "completes"  # nobody on the tour can do it yet
ALONGSIDE = "alongside"  # some are found, more are wished for


def role(need, team_skills):
    """Whether covering an open need completes the team or works alongside those who are
    found; "" once it is covered or promised."""
    if need.is_done:
        return ""
    if need.promised_quantity or (need.skill_id and need.skill_id in team_skills):
        return ALONGSIDE
    return COMPLETES


def gaps(tour):
    """The skills the hosts on the route look for (their events' needs, the communities'
    wishes for skills) that nobody on the tour offers and the tour doesn't look for yet:
    [(skill, [stop labels])], by name. One click makes each a need of the tour."""
    stops = tour.ordered_stops()
    events = {stop.event_id for stop in stops if stop.event_id}
    communities = {stop.community_id for stop in stops if stop.community_id and not stop.event_id}
    if not (events or communities):
        return []
    wanted = (
        Listing.objects.open()
        .filter(type=Listing.TYPE_WISH, kind__in=Listing.SKILL_KINDS, skill__isnull=False)
        .filter(Q(event__in=events) | Q(community__in=communities, event=None))
        .exclude(skill_id__in=tour.team_skill_ids())
        # Without NULLs: NOT IN with a NULL in it would leave nothing
        .exclude(skill_id__in=tour.listings.exclude(skill=None).values("skill_id"))
        .select_related("skill")
    )
    where = {}
    for wish in wanted:
        for stop in stops:
            if stop.event_id:
                here = stop.event_id == wish.event_id
            else:
                here = stop.community_id == wish.community_id and wish.event_id is None
            if here:
                labels = where.setdefault(wish.skill, [])
                if stop.label not in labels:
                    labels.append(stop.label)
    return sorted(where.items(), key=lambda pair: pair[0].get_name().lower())


def add_need(tour, skill):
    """Make a skill the hosts look for a need of the tour: someone who can do it."""
    last = tour.listings.order_by("-order").values_list("order", flat=True).first()
    return Listing.objects.create(
        type=Listing.TYPE_WISH, kind=Listing.KIND_HANDS, skill=skill, tour=tour,
        order=0 if last is None else last + 1,
    )
