"""The calendars in the dashboard.

The ambassador's calendar: a community's projects and the volunteer stays requested and
confirmed for it and its projects, per month, with who brings which skills and things.
Shows how many people are there each day against the community's room for guests, so
overbooking stands out, and which needs of its current and coming projects are still
open. A second view celebrates the needs that are covered, and who covered them.

The lending calendar: when the tools someone lends are borrowed, and by whom, requested
and agreed, and when they borrow tools themselves."""

import calendar as pycalendar
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from communities.models import Community
from projects.models import Project

from gift_economy.gifts.models import Listing

from .models import Match, period_text, until_text

_ACTIVE = (Match.STATUS_PENDING, Match.STATUS_COUNTER, Match.STATUS_ACCEPTED)


@dataclass
class Stay:
    match: Match
    start: date
    end: date
    project: Project | None

    @property
    def confirmed(self):
        return self.match.status == Match.STATUS_ACCEPTED

    @property
    def person(self):
        return self.match.from_user

    def covers(self, day):
        return self.start <= day <= self.end


@dataclass
class Day:
    date: date
    in_month: bool
    is_today: bool
    projects: list = field(default_factory=list)
    stays: list = field(default_factory=list)
    capacity: int | None = None

    @property
    def confirmed(self):
        return sum(1 for stay in self.stays if stay.confirmed)

    @property
    def requested(self):
        return sum(1 for stay in self.stays if not stay.confirmed)

    @property
    def overbooked(self):
        """More confirmed people than there is room for."""
        return self.capacity is not None and self.confirmed > self.capacity

    @property
    def tight(self):
        """Confirmed and requested together would be more than there is room for."""
        return self.capacity is not None and self.confirmed + self.requested > self.capacity


def _month(value):
    try:
        year, month = (int(part) for part in value.split("-"))
        return date(year, month, 1)
    except (AttributeError, ValueError):
        today = timezone.localdate()
        return today.replace(day=1)


def _local_day(value):
    return timezone.localdate(value) if value else None


def stays_of(community):
    """Requested and confirmed stays at the community or one of its projects:
    (dated stays, stays without dates)."""
    project_ids = list(community.projects.values_list("pk", flat=True))
    matches = (
        Match.objects.filter(status__in=_ACTIVE)
        .filter(
            Q(content_type=ContentType.objects.get_for_model(Community), object_id=str(community.pk))
            | Q(content_type=ContentType.objects.get_for_model(Project), object_id__in=[str(pk) for pk in project_ids])
        )
        .select_related("from_user", "content_type", "volunteer_details")
        .prefetch_related("contributions__listing__skill")
    )
    projects = {str(project.pk): project for project in community.projects.all()}
    dated, undated = [], []
    for match in matches:
        start, end = (_local_day(value) for value in match.stay_period())
        project = projects.get(match.object_id) if match.content_type.model == "project" else None
        if not (start or end):
            undated.append(Stay(match, None, None, project))
            continue
        dated.append(Stay(match, start or end, end or start, project))
    dated.sort(key=lambda stay: (stay.start, stay.end))
    return dated, undated


def _ambassadors_community(request, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    if not (request.user.is_staff or request.user == community.owner):
        raise PermissionDenied
    return community


def _with_needs(projects):
    return projects.prefetch_related("listings__skill", "listings__contributions__match__from_user")


@login_required
def calendar(request, community_slug):
    community = _ambassadors_community(request, community_slug)

    first = _month(request.GET.get("month"))
    last = first.replace(day=pycalendar.monthrange(first.year, first.month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=6 - last.weekday())
    today = timezone.localdate()

    projects = list(
        community.projects
        # Manually archived projects are off the calendar; ended ones stay in their months
        .filter(Q(archived_at=None) | Q(ends_on__lt=today))
        .filter(Q(starts_on=None) | Q(starts_on__lte=grid_end))
        .filter(Q(ends_on=None) | Q(ends_on__gte=grid_start))
        .prefetch_related("listings__skill", "listings__contributions__match")
        .order_by("starts_on", "pk")
    )
    stays, undated = stays_of(community)

    weeks = []
    day = grid_start
    while day <= grid_end:
        week = []
        for _ in range(7):
            week.append(Day(
                date=day,
                in_month=day.month == first.month,
                is_today=day == today,
                # Ongoing projects are listed once above the grid instead of on every day
                projects=[p for p in projects if p.ends_on and (p.starts_on or p.ends_on) <= day <= p.ends_on],
                stays=[stay for stay in stays if stay.covers(day)],
                capacity=community.max_guests,
            ))
            day += timedelta(days=1)
        weeks.append(week)

    month_stays = [stay for stay in stays if stay.start <= last and stay.end >= first]
    # What is still missing doesn't depend on the month shown: every running and coming project
    open_needs = [
        (project, [need for need in project.needs() if not need.is_done])
        for project in _with_needs(community.projects.current()).order_by(F("starts_on").asc(nulls_first=True), "pk")
    ]
    previous_month = (first - timedelta(days=1)).replace(day=1)
    next_month = last + timedelta(days=1)
    return render(request, "matches/calendar.html", {
        "community": community,
        "calendar_community": community,
        "month": first,
        "previous_month": previous_month.strftime("%Y-%m"),
        "next_month": next_month.strftime("%Y-%m"),
        "this_month": today.strftime("%Y-%m"),
        "weeks": weeks,
        "ongoing_projects": [p for p in projects if p.is_ongoing],
        "weekdays": [weeks[0][i].date for i in range(7)],
        "month_stays": month_stays,
        "undated_stays": undated,
        "open_needs": [(project, needs) for project, needs in open_needs if needs],
        "complete_projects": [project for project, needs in open_needs if not needs],
        "covered_count": sum(len(project.needs()) - len(needs) for project, needs in open_needs),
        "overbooked_days": [d for week in weeks for d in week if d.in_month and d.overbooked],
        "tight_days": [d for week in weeks for d in week if d.in_month and d.tight and not d.overbooked],
    })


@login_required
def covered(request, community_slug):
    """What all the help has made possible: the covered and promised needs of the
    community's projects, newest projects first, each with who brings it."""
    community = _ambassadors_community(request, community_slug)
    projects = (
        _with_needs(community.projects.all())
        .prefetch_related("listings__contributions__match__references")
        .order_by(F("starts_on").desc(nulls_first=True), "-pk")
    )
    covered_needs = []
    for project in projects:
        needs = [(need, _helpers(need, community)) for need in project.needs() if need.is_done]
        if needs:
            covered_needs.append((project, needs))
    helpers = {helper.person for _, needs in covered_needs for _, people in needs for helper in people}
    return render(request, "matches/calendar_covered.html", {
        "community": community,
        "calendar_community": community,
        "covered_needs": covered_needs,
        "need_count": sum(len(needs) for _, needs in covered_needs),
        "helper_count": len(helpers),
    })


@dataclass
class Helper:
    person: object
    match: Match
    # Whether the ambassador has written them a reference for it yet
    thanked: bool


def _helpers(need, community):
    """Who brings the need, by accepted exchanges, in the order they offered: each person
    once, with the first of their exchanges."""
    helpers = []
    for contribution in sorted(need.contributions.all(), key=lambda c: c.match.created_at):
        match = contribution.match
        person = match.from_user
        if match.status != Match.STATUS_ACCEPTED or person == community.owner or person in [h.person for h in helpers]:
            continue
        thanked = any(reference.author_id == community.owner_id for reference in match.references.all())
        helpers.append(Helper(person, match, thanked))
    return helpers


# ── Lending calendar ────────────────────────────────────────────────

@dataclass
class Lending:
    """A loan as one side sees it: their tool or vehicle lent, or one they borrow; for
    whole days or some hours (Loan)."""

    match: Match
    starts_at: datetime
    ends_at: datetime
    tool: object
    # Whether it is their tool (lent out), else one they borrow
    lent_out: bool

    @property
    def confirmed(self):
        return self.match.status == Match.STATUS_ACCEPTED

    @property
    def person(self):
        """The other side: who borrows it, or who lends it."""
        return self.match.borrower if self.lent_out else self.match.lender

    @property
    def start(self):
        """The first day."""
        return timezone.localdate(self.starts_at)

    @property
    def end(self):
        """The last day (whole days end at the midnight after it)."""
        return timezone.localdate(self.ends_at - timedelta(microseconds=1))

    @property
    def period(self):
        return period_text(self.starts_at, self.ends_at)

    @property
    def until(self):
        return until_text(self.starts_at, self.ends_at)

    @property
    def hours(self):
        """"14:00–18:00" if it is for some hours of one day, else ""."""
        start, end = timezone.localtime(self.starts_at), timezone.localtime(self.ends_at)
        if self.start != self.end or (start.time() == end.time() == time()):
            return ""
        return f"{start:%H:%M}–{end:%H:%M}"

    def covers(self, day):
        return self.start <= day <= self.end

    def overlaps(self, other):
        return self.starts_at < other.ends_at and self.ends_at > other.starts_at


@dataclass
class LendingDay:
    date: date
    in_month: bool
    is_today: bool
    lendings: list = field(default_factory=list)

    @property
    def clashes(self):
        """Their things asked for at the same time on this day by more people than there
        are of them, if they said yes to all."""
        lent = [lending for lending in self.lendings if lending.lent_out]
        tools = {}
        for lending in lent:
            at_once = sum(1 for other in lent if other.tool.pk == lending.tool.pk and other.overlaps(lending))
            if at_once > (lending.tool.quantity or 1):
                tools[lending.tool.pk] = lending.tool
        return list(tools.values())


def lendings_of(user=None, community=None):
    """The requested and agreed loans of what the user lends or borrows themselves, or of
    what a community lends (its tool library) or wishes to borrow, by start."""
    matches = (
        Match.objects.filter(status__in=_ACTIVE, loan__isnull=False)
        .select_related("loan", "from_user", "recipient", "content_type")
        .prefetch_related("target")
    )
    if community is not None:
        own = community.listings.filter(lend=True).values_list("pk", flat=True)
        matches = matches.filter(
            content_type=ContentType.objects.get_for_model(Listing), object_id__in=[str(pk) for pk in own],
        )
    else:
        matches = matches.filter(Q(from_user=user) | Q(recipient=user))
    lendings = []
    for match in matches:
        tool = match.target
        if tool is None:
            continue
        if community is not None:
            lent_out = tool.is_offer
        elif tool.community_id and match.recipient == user:
            # Answered as the community's ambassador: that is in the community's calendar
            continue
        else:
            lent_out = match.lender == user
        starts_at, ends_at = match.loan_period()
        lendings.append(Lending(match, starts_at, ends_at, tool, lent_out=lent_out))
    lendings.sort(key=lambda lending: (lending.starts_at, lending.ends_at))
    return lendings


def _lending_page(request, lendings, tools, **context):
    """A month of loans like the ambassador's calendar, the tools to lend with where they
    are today, and the loans of the month: lent out and borrowed."""
    first = _month(request.GET.get("month"))
    last = first.replace(day=pycalendar.monthrange(first.year, first.month)[1])
    grid_start = first - timedelta(days=first.weekday())
    grid_end = last + timedelta(days=6 - last.weekday())
    today = timezone.localdate()

    weeks = []
    day = grid_start
    while day <= grid_end:
        week = []
        for _ in range(7):
            week.append(LendingDay(
                date=day, in_month=day.month == first.month, is_today=day == today,
                lendings=[lending for lending in lendings if lending.covers(day)],
            ))
            day += timedelta(days=1)
        weeks.append(week)

    now = timezone.now()
    agreed = [lending for lending in lendings if lending.lent_out and lending.confirmed]
    for tool in tools:
        # Where it is right now, and when it is lent next
        tool.lent_now = [lending for lending in agreed if lending.tool.pk == tool.pk and lending.starts_at <= now < lending.ends_at]
        tool.lent_next = next((lending for lending in agreed if lending.tool.pk == tool.pk and lending.starts_at > now), None)

    month_lendings = [lending for lending in lendings if lending.start <= last and lending.end >= first]
    previous_month = (first - timedelta(days=1)).replace(day=1)
    next_month = last + timedelta(days=1)
    return render(request, "matches/lending_calendar.html", {
        "month": first,
        "previous_month": previous_month.strftime("%Y-%m"),
        "next_month": next_month.strftime("%Y-%m"),
        "this_month": today.strftime("%Y-%m"),
        "weeks": weeks,
        "weekdays": [weeks[0][i].date for i in range(7)],
        "tools": tools,
        "lent_out": [lending for lending in month_lendings if lending.lent_out],
        "borrowed": [lending for lending in month_lendings if not lending.lent_out],
        "clash_days": [d for week in weeks for d in week if d.in_month and d.clashes],
        **context,
    })


@login_required
def lending(request):
    """What the user lends themselves, when and to whom; and what they borrow, so they
    know when to bring it back. A community's tool library has its own calendar."""
    tools = list(Listing.objects.of(request.user).to_lend().order_by("title"))
    return _lending_page(request, lendings_of(request.user), tools)


@login_required
def community_lending(request, community_slug):
    """A community's tool library for its ambassador: who borrows which of its tools,
    cargo bike, car or trailer when, requested and agreed, and where each is today."""
    community = _ambassadors_community(request, community_slug)
    tools = list(community.listings.to_lend().order_by("title"))
    return _lending_page(
        request, lendings_of(community=community), tools,
        community=community, lending_community=community,
    )
