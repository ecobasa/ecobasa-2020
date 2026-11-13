"""What a tour still looks for, found from its route, and why someone who covers a
need would say yes; and the tours that fit a person.

The people a need fits are found by the general matching (gift_economy.matches.matching):
a tour's need is a wish whose place is the tour's route."""

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.measure import D
from django.db.models import Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from gift_economy.gifts.models import Listing
from gift_economy.matches.emails import notify_new_suggestions
from gift_economy.matches.matching import distance_km, km_to_route
from gift_economy.matches.models import Suggestion

REASON_STAY = Suggestion.REASON_STAY
REASON_ROUTE = Suggestion.REASON_ROUTE
REASON_LEARN = Suggestion.REASON_LEARN
REASON_HAS = Suggestion.REASON_HAS
REASON_WANTS = Suggestion.REASON_WANTS
REASON_HOME = Suggestion.REASON_HOME
REASON_TOGETHER = Suggestion.REASON_TOGETHER

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


# ── Tours that fit a person ─────────────────────────────────────────
# A tour is suggested to someone who could travel along: it stops where they stay
# around their days, a stop on it offers a thing they wish for, it passes near where
# they live, or it wants to learn what they wish to learn. One such suggestion per tour,
# the first reason in this order; joining it opens with the stretch that fits already
# chosen. While they pause tour suggestions (User.tours_paused) only their stays count.
# And a tour that passes by them and goes to a stop that wishes for a thing they have
# could take it along: one more suggestion per tour, also while they pause.
# That their skill covers one of its needs is suggested with the need itself
# (gift_economy.matches.matching).

# Days before and after a stay in which a stop is still "around your days"
AROUND_DAYS = 3


@dataclass
class Fit:
    tour: object
    reason: str
    own: object  # what it fits: a stay (Match), a wish to learn (Listing), or the person
    from_stop: object = None  # None: from the start
    to_stop: object = None  # None: to the end
    km: int | None = None
    detail: object = None  # the offer or wish at a stop it is about

    @property
    def join_url(self):
        return self.tour.join_url(self.from_stop, self.to_stop)


def joinable(user):
    """The tours `user` could ask to join: published, shown in the list, current,
    looking for travellers, someone else's, and they aren't on it or asked yet."""
    from gift_economy.matches.models import Match

    from .models import Tour, Traveller

    taken = Traveller.objects.filter(user=user).filter(
        Q(match=None) | ~Q(match__status__in=Match.CLOSED_STATUSES)
    ).values("tour_id")
    return (
        Tour.objects.published().listed().current().filter(open_to_join=True, organiser__isnull=False)
        .exclude(organiser=user).exclude(pk__in=taken)
    )


def stays_of(user):
    """Their stays at communities and events that are open or accepted and not over (not
    the tour visits they asked for as organisers: those are the tour's own)."""
    from gift_economy.matches.models import STAY_APP_LABELS, Match

    today = timezone.localdate()
    return (
        Match.objects.filter(
            from_user=user, content_type__app_label__in=STAY_APP_LABELS,
            status__in=(Match.STATUS_PENDING, Match.STATUS_COUNTER, Match.STATUS_ACCEPTED),
        )
        .filter(tour_stop=None)
        .filter(Q(stay_details=None) | Q(stay_details__stay_to=None) | Q(stay_details__stay_to__date__gte=today))
        .select_related("content_type", "stay_details")
    )


def _stops_at(stay):
    """Where a stay is, as stops: at an event (or its community without an event), or
    at a community (also at its events)."""
    from .models import Stop

    target = stay.target
    if target is None:
        return Stop.objects.none()
    if target._meta.model_name == "event":
        return Stop.objects.filter(Q(event=target) | Q(community=target.community_id, event=None))
    return Stop.objects.filter(community=target)


def stay_days(stay):
    """(first, last) day of a stay, either None if it isn't said."""
    details = getattr(stay, "stay_details", None)
    if details is None:
        return None, None
    return (
        timezone.localdate(details.stay_from) if details.stay_from else None,
        timezone.localdate(details.stay_to) if details.stay_to else None,
    )


def around(stop, first, last):
    """Whether a stop's days are within AROUND_DAYS of a stay's. A stop without days is
    not; a stay without days fits any."""
    arrive, leave = stop.arrive_on or stop.leave_on, stop.leave_on or stop.arrive_on
    if arrive is None:
        return False
    margin = timedelta(days=AROUND_DAYS)
    return (last is None or arrive <= last + margin) and (first is None or leave >= first - margin)


def around_days(days, first, last):
    """Whether two stays' (first, last) days are within AROUND_DAYS of each other; days
    not said fit any."""
    start, end = days
    margin = timedelta(days=AROUND_DAYS)
    return (last is None or start is None or start <= last + margin) and (
        first is None or end is None or end >= first - margin
    )


def _nearest(stops, point):
    """Of `stops`, the one nearest `point` as everyone sees it (the first without a point)."""
    def km(stop):
        place = stop.public_place()[1]
        return distance_km(point, place) if place is not None else float("inf")

    return min(stops, key=km) if point is not None else stops[0]


def _fits_stay(user, stay, stop):
    """The Fit for travelling to `stop` for a stay there: getting on at the stop before
    it nearest them, off there (from there to the end if it is the first). None if there
    is no room for the stay's people on that stretch."""
    tour = stop.tour
    stops = tour.ordered_stops()
    index = next(i for i, s in enumerate(stops) if s.pk == stop.pk)
    if index == 0:
        start, end = stop, None
    else:
        start, end = _nearest(stops[:index], user.location), stop
    if not tour.fits(start, end, stay.people):
        return None
    return Fit(tour, REASON_STAY, stay, start, end)


def by_stay(user, tours, stays=None):
    """Tours that stop where `user` stays (or asked to), around their days."""
    found = []
    for stay in stays_of(user) if stays is None else stays:
        first, last = stay_days(stay)
        stops = _stops_at(stay).filter(tour__in=tours).select_related("tour", "event", "community")
        for stop in stops:
            if around(stop, first, last):
                fit = _fits_stay(user, stay, stop)
                if fit is not None:
                    found.append(fit)
    return found


# ── Rides ──
# A ride (two stops, neither with a host) only helps someone who needs to go where it
# goes: it is suggested to who stays near where it ends, around its day, and lives
# within their distance of where it starts. Never for just passing by.

# How far from where a ride ends a stay may be
RIDE_END_KM = 30


def rides(tours):
    """Of `tours`, the rides (Tour.is_ride, in one query)."""
    from django.db.models import Count

    return tours.filter(open_to_join=True).annotate(
        stop_count=Count("stops", distinct=True),
        hosted=Count("stops", filter=Q(stops__community__isnull=False), distinct=True),
    ).filter(stop_count=2, hosted=0)


def _stay_point(stay):
    """Where a stay is, as everyone may see it."""
    target = stay.target
    community = getattr(target, "community", target)
    return community.rough_place()[1] if community is not None else None


def by_ride(user, tours, stays=None):
    """Rides that end near where `user` stays (or asked to), around the ride's day, and
    start within their distance of where they live."""
    if user.location is None:
        return []
    stays = list(stays_of(user) if stays is None else stays)
    if not stays:
        return []
    found = []
    for tour in rides(tours).prefetch_related("stops"):
        start, end = tour.ordered_stops()
        start_point, end_point = start.public_place()[1], end.public_place()[1]
        if start_point is None or end_point is None:
            continue
        if distance_km(user.location, start_point) > (user.match_radius or 0):
            continue
        day = start.leave_on or start.arrive_on or end.arrive_on
        for stay in stays:
            point = _stay_point(stay)
            if point is None or distance_km(point, end_point) > RIDE_END_KM:
                continue
            first, last = stay_days(stay)
            if day is not None and around_days((day, day), first, last) and tour.fits(start, end, stay.people):
                found.append(Fit(tour, REASON_STAY, stay, start, end))
                break
    return found


def towards_home(user, start, end):
    """Whether a ride from `start` to `end` takes `user` home: it ends within their
    distance of where they live, or brings them at least a third of the way."""
    home = user.location
    from_start, from_end = distance_km(start, home), distance_km(end, home)
    return from_end <= (user.match_radius or 0) or from_end <= from_start * 2 / 3


def by_ride_home(user, tours, stays=None):
    """Rides that start near where `user` stays (or asked to), around the stay's last
    day, and go towards their home."""
    if user.location is None:
        return []
    stays = list(stays_of(user) if stays is None else stays)
    if not stays:
        return []
    found = []
    for tour in rides(tours).prefetch_related("stops"):
        start, end = tour.ordered_stops()
        start_point, end_point = start.public_place()[1], end.public_place()[1]
        if start_point is None or end_point is None:
            continue
        # Who lives near where it starts isn't going home with it
        if distance_km(user.location, start_point) <= (user.match_radius or 0):
            continue
        if not towards_home(user, start_point, end_point):
            continue
        day = start.leave_on or start.arrive_on or end.arrive_on
        for stay in stays:
            point = _stay_point(stay)
            if point is None or distance_km(point, start_point) > RIDE_END_KM:
                continue
            first, last = stay_days(stay)
            leaving = (last, last) if last else (first, None)
            if day is not None and around_days((day, day), *leaving) and tour.fits(start, end, stay.people):
                found.append(Fit(tour, REASON_HOME, stay, start, end))
                break
    return found


def passes_near(user, tours):
    """Of `tours`, those with dates whose route passes within `user`'s distance of
    where they live."""
    if user.location is None:
        return tours.none()
    return tours.exclude(route=None).exclude(starts_on=None).filter(
        route__dwithin=(user.location, D(km=user.match_radius or 0)),
    )


def by_route(user, tours):
    """Tours with dates that pass near where `user` lives: getting on at the stop
    nearest them (not the last), to the end."""
    found = []
    for tour in passes_near(user, tours).exclude(pk__in=rides(tours).values("pk")):
        stops = tour.ordered_stops()
        start = _nearest(stops[:-1] or stops, user.location)
        if tour.fits(start, None, 1):
            found.append(Fit(tour, REASON_ROUTE, user, start, None, round(km_to_route(user.location, tour.route))))
    return found


def passes_by(user, tours):
    """Of `tours`, those passing within `user`'s distance of where they live, or through
    their country."""
    near = Q(pk__in=[])
    if user.location is not None:
        near |= Q(route__dwithin=(user.location, D(km=user.match_radius or 0)))
    if user.country:
        # Stored as "DE,NL,FR"
        near |= Q(countries__regex=rf"(^|,){user.country.code}(,|$)")
    return tours.filter(near)


def _at_stop(stop):
    """The things a stop's host offers or wishes for: an event's (and its community's own
    there), or a community's (with its events')."""
    things = Listing.objects.current().filter(kind__in=Listing.THING_KINDS, tour=None)
    if stop.event_id:
        return things.filter(Q(event=stop.event_id) | Q(community=stop.community_id, event=None))
    return things.filter(community=stop.community_id)


def by_gifts(user, tours, travel=True):
    """Tours passing by `user` with a stop that offers a thing they wish for (to travel
    there along, if `travel`) or wishes for a thing they offer (to give to the tour to
    take along): at most one Fit of each per tour, the first stop that has one."""
    from gift_economy.matches.matching import fit as fits_together, side_of

    own = [
        (listing, side_of(listing))
        for listing in Listing.objects.current().filter(owner=user, community=None, tour=None, kind__in=Listing.THING_KINDS)
    ]
    own = [(listing, side) for listing, side in own if side is not None and (travel or listing.is_offer)]
    if not own:
        return []
    found = []
    for tour in passes_by(user, tours).prefetch_related("stops__event", "stops__community"):
        stops = tour.ordered_stops()
        taken = set()
        for index, stop in enumerate(stops):
            if not stop.community_id:
                continue
            for theirs in _at_stop(stop).select_related("owner", "community__owner", "event__community", "skill"):
                side = side_of(theirs)
                if side is None or side.owner == user:
                    continue
                for listing, mine in own:
                    reason = REASON_HAS if listing.is_wish else REASON_WANTS
                    if reason in taken or fits_together(mine, side) is None:
                        continue
                    if reason == REASON_HAS:
                        start = stop if index == 0 else _nearest(stops[:index], user.location)
                        end = None if index == 0 else stop
                        if not tour.fits(start, end, 1):
                            continue
                        found.append(Fit(tour, reason, listing, start, end, detail=theirs))
                    else:
                        found.append(Fit(tour, reason, listing, detail=theirs))
                    taken.add(reason)
    return found


def _wishes_to_learn(user):
    return Listing.objects.open().filter(
        owner=user, community=None, type=Listing.TYPE_WISH, kind=Listing.KIND_SKILL, skill__isnull=False,
    ).select_related("skill")


def fits_skills(user):
    """The pks of tours one of whose open needs `user` can cover with a skill they offer,
    or that want to learn what they wish to learn (a queryset of pks)."""
    from .models import Tour

    offers = Listing.objects.open().filter(
        owner=user, community=None, type=Listing.TYPE_OFFER, skill__isnull=False,
    ).exclude(available=False).values("skill_id")
    needs = Listing.objects.open().filter(type=Listing.TYPE_WISH, tour__isnull=False, skill_id__in=offers)
    return Tour.objects.filter(
        Q(pk__in=needs.values("tour_id")) | Q(learn_skills__in=_wishes_to_learn(user).values("skill_id"))
    ).values("pk")


def reaches(user, tour):
    """Whether a tour is where `user` looks, by their settings, as for their wishes: its
    route (or start) within their distance, or in their country, or anywhere."""
    if user.match_global:
        return True
    if user.location is not None:
        if tour.route is not None:
            return km_to_route(user.location, tour.route) <= (user.match_radius or 0)
        if tour.start is not None:
            return distance_km(user.location, tour.start) <= (user.match_radius or 0)
    if user.country:
        return user.country.code in {country.code for country in tour.countries}
    return user.location is None


def by_learning(user, tours):
    """Tours that want to learn what `user` wishes to learn, tour ideas too."""
    wishes = {wish.skill_id: wish for wish in _wishes_to_learn(user)}
    if not wishes:
        return []
    found = []
    for tour in tours.filter(learn_skills__in=wishes).exclude(pk__in=rides(tours).values("pk")).distinct().prefetch_related("learn_skills"):
        if not reaches(user, tour) or not tour.fits(None, None, 1):
            continue
        wish = next(wishes[skill.pk] for skill in tour.learn_skills.all() if skill.pk in wishes)
        found.append(Fit(tour, REASON_LEARN, wish))
    return found


def tours_for(user, tours=None):
    """The tours that fit `user`, one Fit per tour by its first reason: they stay where
    it goes, it passes near them, it wants to learn what they do."""
    if not user.is_authenticated:
        return []
    tours = joinable(user) if tours is None else tours & joinable(user)
    travel = not user.tours_paused
    gifts = by_gifts(user, tours, travel=travel)
    fits = [
        *by_stay(user, tours), *by_ride(user, tours), *by_ride_home(user, tours),
        *[fit for fit in gifts if fit.reason == REASON_HAS],
    ]
    if travel:
        fits += [*by_route(user, tours), *by_learning(user, tours)]
    found = {}
    for fit in fits:
        found.setdefault(fit.tour.pk, fit)
    giving = {}
    for fit in gifts:
        if fit.reason == REASON_WANTS:
            giving.setdefault(fit.tour.pk, fit)
    return [*found.values(), *giving.values()]


def stretch_for(tour, suggestion):
    """(from stop, to stop) a suggestion's join page opens with, worked out again from
    the tour as it is now: (None, None) for the whole route."""
    user, own, reason = suggestion.user, suggestion.own, suggestion.reason
    if reason == REASON_HAS and suggestion.detail is not None:
        stops = tour.ordered_stops()
        for index, stop in enumerate(stops):
            if stop.community_id and _at_stop(stop).filter(pk=suggestion.detail.pk).exists():
                return (stop, None) if index == 0 else (_nearest(stops[:index], user.location), stop)
    if reason in (REASON_STAY, REASON_HOME) and own is not None and tour.is_ride:
        return None, None
    if reason == REASON_STAY and own is not None:
        first, last = stay_days(own)
        for stop in _stops_at(own).filter(tour=tour):
            if around(stop, first, last):
                fit = _fits_stay(user, own, stop)
                if fit is not None:
                    return fit.from_stop, fit.to_stop
    if reason == REASON_ROUTE and user.location is not None:
        stops = tour.ordered_stops()
        if stops:
            return _nearest(stops[:-1] or stops, user.location), None
    return None, None


def _stop_with(tour, listing):
    """The first stop whose host offers or wishes for `listing`."""
    if listing is None:
        return None
    return next((stop for stop in tour.ordered_stops() if stop.community_id and _at_stop(stop).filter(pk=listing.pk).exists()), None)


def message_for(tour, suggestion):
    """A message for acting on a tour's suggestion, in the reader's language, to change
    as they like: asking to join, or offering a thing to a stop's host."""
    reason, own, detail = suggestion.reason, suggestion.own, suggestion.detail
    if reason == REASON_WANTS:
        stop = _stop_with(tour, detail)
        day = stop and (stop.arrive_on or stop.leave_on)
        values = {"tour": tour.title, "title": own.display_title if own else ""}
        if day:
            return _(
                "The tour %(tour)s comes to you around %(date)s and passes through my country. "
                "I could give them my %(title)s to bring along."
            ) % {**values, "date": date_format(day, "MONTH_DAY_FORMAT")}
        return _(
            "The tour %(tour)s comes to you and passes through my country. I could give them my %(title)s to bring along."
        ) % values
    start = stretch_for(tour, suggestion)[0] or next(iter(tour.ordered_stops()), None)
    stop = start.label if start is not None else ""
    if reason == REASON_STAY and own is not None:
        target = own.target
        place = target.get_match_display_name() if target is not None else ""
        first = stay_days(own)[0]
        if first:
            return _(
                "I'm staying at %(place)s from %(from)s and would like to travel there with you from %(stop)s."
            ) % {"place": place, "from": date_format(first, "MONTH_DAY_FORMAT"), "stop": stop}
        return _("I'm staying at %(place)s and would like to travel there with you from %(stop)s.") % {
            "place": place, "stop": stop,
        }
    if reason == REASON_HOME and own is not None:
        target = own.target
        return _("I'm staying at %(place)s and would like to ride back towards home with you.") % {
            "place": target.get_match_display_name() if target is not None else "",
        }
    if reason == REASON_ROUTE:
        return _("You pass near where I live; I'd like to come along from %(stop)s.") % {"stop": stop}
    if reason == REASON_LEARN and own is not None:
        return _("I'd like to learn %(skill)s too and would love to learn it together.") % {"skill": own.display_title}
    if reason == REASON_HAS and detail is not None:
        return _("%(place)s offers %(title)s, which I'm looking for; I'd like to travel there with you.") % {
            "place": detail.event.title if detail.event_id else detail.community.name, "title": detail.display_title,
        }
    return ""


# ── Suggesting them ─────────────────────────────────────────────────

def _tour_type():
    from .models import Tour

    return ContentType.objects.get_for_model(Tour)


def _group(reason):
    # Travelling along, or giving something along: one suggestion of each per tour
    return "give" if reason == REASON_WANTS else "travel"


def suggest(user, fits):
    """A suggestion for each fit, unless the tour was suggested to them before for the
    same (travelling along, or giving along; also when they hid it). Returns the new ones."""
    tour_type = _tour_type()
    known = {
        (other_id, _group(reason))
        for other_id, reason in Suggestion.objects.filter(user=user, other_type=tour_type).values_list("other_id", "reason")
    }
    created = []
    for fit in fits:
        key = (str(fit.tour.pk), _group(fit.reason))
        if key in known:
            continue
        detail = {}
        if fit.detail is not None:
            detail = {"detail_type": ContentType.objects.get_for_model(fit.detail), "detail_id": str(fit.detail.pk)}
        created.append(Suggestion.objects.create(
            user=user, own_type=ContentType.objects.get_for_model(fit.own), own_id=str(fit.own.pk),
            other_type=tour_type, other_id=str(fit.tour.pk), other_user=fit.tour.organiser,
            kind=Suggestion.KIND_TOURS, reason=fit.reason, distance_km=fit.km, **detail,
        ))
        known.add(key)
    return created


def suggest_for(user, notify=True):
    """Find the tours that fit `user` now and suggest the new ones."""
    created = suggest(user, tours_for(user))
    if notify and created:
        notify_new_suggestions({user})
    return created


def _people_for(tour):
    """Who a tour could fit, roughly: who stays at its stops' hosts, who lives within the
    longest distance anyone looks from its route, who wishes to learn what it wants to.
    tours_for then decides for each."""
    from django.contrib.auth import get_user_model

    from gift_economy.matches.models import STAY_APP_LABELS, Match

    from events.models import Event

    User = get_user_model()
    # An event's stop is at its community too: a stay at the community or any of its events
    communities = {stop.community_id for stop in tour.ordered_stops() if stop.community_id}
    if tour.is_ride:
        from communities.models import Community

        # Who stays near where it ends (a ride there) or starts (a ride home). Roughly:
        # rough_place moves a private place by a few km at most
        for stop in (tour.ordered_stops()[0], tour.ordered_stops()[-1]):
            point = stop.public_place()[1]
            if point is not None:
                communities |= set(Community.objects.filter(
                    location__dwithin=(point, D(km=RIDE_END_KM + 5)),
                ).values_list("pk", flat=True))
    events = Event.objects.filter(community__in=communities).values_list("pk", flat=True)
    stays = Match.objects.filter(content_type__app_label__in=STAY_APP_LABELS).filter(
        Q(content_type__model="community", object_id__in=[str(pk) for pk in communities])
        | Q(content_type__model="event", object_id__in=[str(pk) for pk in events])
    )
    people = Q(pk__in=stays.values("from_user"))
    if tour.route is not None and tour.starts_on is not None:
        people |= Q(location__dwithin=(tour.route, D(km=NEAR_KM_MAX)))
    people |= Q(pk__in=Listing.objects.open().filter(
        type=Listing.TYPE_WISH, kind=Listing.KIND_SKILL, community=None, skill__in=tour.learn_skills.all(),
    ).values("owner"))
    people |= Q(pk__in=_fitting_owners(tour))
    return User.objects.filter(people, is_active=True).exclude(pk=tour.organiser_id).distinct()


def _fitting_owners(tour):
    """The people with a thing that fits a thing the hosts on the route offer or wish for
    (the general matching's candidates, roughly nearby)."""
    from gift_economy.matches.matching import candidates, fit as fits_together, side_of

    owners = set()
    for stop in tour.ordered_stops():
        if not stop.community_id:
            continue
        for theirs in _at_stop(stop):
            side = side_of(theirs)
            if side is None:
                continue
            for listing in candidates(side).filter(community=None, tour=None, owner__isnull=False):
                mine = side_of(listing)
                if mine is not None and fits_together(mine, side) is not None:
                    owners.add(listing.owner_id)
    return owners


# The farthest anyone is looked for from a route ("passes near you" uses each one's own
# distance, see by_route)
NEAR_KM_MAX = 500


def suggest_tour(tour, notify=True):
    """Suggest a tour to everyone it fits, or forget what was suggested about it once
    nobody can join it any more. Returns the new suggestions."""
    from .models import Tour

    if not joinable_by_anyone(tour):
        forget_tour(tour)
        return []
    created = []
    for person in _people_for(tour):
        created += suggest(person, tours_for(person, Tour.objects.filter(pk=tour.pk)))
    if notify:
        notify_new_suggestions({s.user for s in created})
    return created


def joinable_by_anyone(tour):
    return tour.is_published and tour.listed and tour.is_current and tour.open_to_join and tour.organiser_id


def forget_tour(tour, user=None):
    """Remove the suggestions of a tour (for one person), but not those someone hid: a
    hidden tour isn't suggested again."""
    found = Suggestion.objects.filter(other_type=_tour_type(), other_id=str(tour.pk), dismissed_at=None)
    if user is not None:
        found = found.filter(user=user)
    found.delete()


def forget_stay(stay):
    """A stay that was declined or withdrawn suggests no tours any more, nor its
    person to others who come."""
    stay_type, pk = ContentType.objects.get_for_model(stay), str(stay.pk)
    Suggestion.objects.filter(kind=Suggestion.KIND_TOURS, dismissed_at=None).filter(
        Q(own_type=stay_type, own_id=pk) | Q(other_type=stay_type, other_id=pk)
    ).delete()


# ── Going together ──────────────────────────────────────────────────
# Two people coming to the same event or community around the same days, living within
# each one's distance of the other: each is suggested to the other, to go there together.
# Only accepted stays (and who just comes to an open event), never open requests: at an
# event who comes is shown to people logged in anyway, at a community they would likely
# meet there anyway.

def coming_with(stay):
    """The other accepted stays at the same event or community as `stay`, around its
    days, of people living within the stay's person's distance; [(their stay, km)]."""
    from gift_economy.matches.models import Match

    user = stay.from_user
    if user.location is None or stay.status != Match.STATUS_ACCEPTED or getattr(stay, "tour_stop", None):
        return []
    days = stay_days(stay)
    found = []
    others = (
        Match.objects.filter(
            content_type=stay.content_type, object_id=stay.object_id, status=Match.STATUS_ACCEPTED, tour_stop=None,
        ).exclude(from_user=user).exclude(from_user__location=None)
        .select_related("from_user", "stay_details", "content_type")
    )
    for other in others:
        km = distance_km(user.location, other.from_user.location)
        if km <= (user.match_radius or 0) and around_days(stay_days(other), *days):
            found.append((other, km))
    return found


def suggest_together(stay, notify=True):
    """Suggest the people from nearby who come to the same place in the same days, and
    this stay's person to them (each within their own distance). Returns the new ones."""
    stay_type = ContentType.objects.get_for_model(stay)
    created = []
    for other, km in coming_with(stay):
        pairs = [(stay, other)]
        if km <= (other.from_user.match_radius or 0):
            pairs.append((other, stay))
        for own, theirs in pairs:
            suggestion, new = Suggestion.objects.get_or_create(
                user=own.from_user, own_type=stay_type, own_id=str(own.pk), other_type=stay_type, other_id=str(theirs.pk),
                defaults={
                    "other_user": theirs.from_user, "kind": Suggestion.KIND_TOURS,
                    "reason": REASON_TOGETHER, "distance_km": round(km),
                },
            )
            if new:
                created.append(suggestion)
    if notify and created:
        notify_new_suggestions({s.user for s in created})
    return created


def suggest_everything():
    """Suggest all current tours to the people they fit, e.g. after deploying this.
    Returns how many suggestions were created."""
    from .models import Tour

    from gift_economy.matches.models import STAY_APP_LABELS, Match

    count = sum(len(suggest_tour(tour, notify=False)) for tour in Tour.objects.published().listed().current())
    stays = Match.objects.filter(content_type__app_label__in=STAY_APP_LABELS, status=Match.STATUS_ACCEPTED, tour_stop=None)
    return count + sum(len(suggest_together(stay, notify=False)) for stay in stays.select_related("from_user", "content_type"))
