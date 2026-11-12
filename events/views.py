from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from communities.models import Community
from dashboard_lists import Choice, paginate, query_url
from gift_economy.matches.emails import notify_match_created
from gift_economy.gifts.models import Listing
from gift_economy.matches.matching import distance_km
from gift_economy.matches.models import Contribution, Match, StayDetails
from gift_economy.gifts.skills.models import skill_name_q

from . import kinds
from .forms import ComingForm, EventForm, HelpOfferForm, NeedFormSet
from .freshness import read_confirm_token
from .models import Event

# An event's needs and skills to learn, with how far each is covered
_LISTINGS = Prefetch(
    "listings", queryset=Listing.objects.select_related("skill").prefetch_related(
        "categories", "contributions__match__from_user",
    ),
)


def _events():
    return Event.objects.select_related("community", "community__owner").prefetch_related(_LISTINGS)


def _event(community_slug, slug, events=None):
    return get_object_or_404(_events() if events is None else events, community__slug=community_slug, slug=slug)


@login_required
def nearby(request):
    """The current events around the place in one's profile, nearest first: within the
    distance one looks for matches in, or everywhere. Filtered by a search and by kind.
    Distances are to where everyone sees a community, so they give no private place away."""
    user = request.user
    events = _events().current()
    q = (request.GET.get("q") or "").strip()
    if q:
        events = events.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(community__name__icontains=q)
            | Q(community__location_name__icontains=q)
            | Q(listings__title__icontains=q)
            | skill_name_q(q, "listings__skill__")
        ).distinct()

    everywhere = request.GET.get("where") == "everywhere" or user.location is None
    found = []
    for event in events:
        point = event.place.rough_place()[1]
        event.km = round(distance_km(user.location, point)) if user.location is not None and point is not None else None
        if everywhere or (event.km is not None and event.km <= user.match_radius):
            found.append(event)
    # Nearest first; those without a place last, freshest first among equals
    found.sort(key=lambda event: (event.km is None, event.km or 0, -event.updated_at.timestamp()))

    kind = request.GET.get("kind", "")
    kind_choices = [Choice(_("All"), query_url(request, kind=None), not kind, len(found))] + [
        Choice(
            kinds.TEXTS[value]["plural"], query_url(request, kind=value), kind == value,
            sum(1 for event in found if event.kind == value), icon=kinds.ICONS[value],
        )
        for value, _label in kinds.CHOICES
    ]
    if kind in kinds.TEXTS:
        found = [event for event in found if event.kind == kind]
    wheres = []
    if user.location is not None:
        wheres = [
            Choice(
                _("Within %(km)s km") % {"km": user.match_radius}, query_url(request, where=None),
                not everywhere, icon="fa-location-dot",
            ),
            Choice(_("Everywhere"), query_url(request, where="everywhere"), everywhere, icon="fa-earth-europe"),
        ]
    page = paginate(request, found)
    return render(request, "events/nearby.html", {
        "page": page,
        "events": page.object_list,
        "q": q,
        "wheres": wheres,
        "kinds": kind_choices,
        "has_place": user.location is not None,
        "everywhere": everywhere,
    })


def detail(request, community_slug, slug):
    event = _event(community_slug, slug)
    can_edit = event.can_edit(request.user)
    if event.archived_at and not can_edit:
        messages.info(request, event.texts["archived"])
    matches = list(
        event.matches.select_related("from_user", "stay_details")
        .prefetch_related("contributions__listing__skill").exclude(status__in=Match.CLOSED_STATUSES)
    )
    coming = [match for match in matches if match.status == Match.STATUS_ACCEPTED]
    own_match = None
    if request.user.is_authenticated:
        own_match = next((match for match in matches if match.from_user == request.user), None)
    return render(request, "events/event_detail.html", {
        "event": event,
        "community": event.community,
        "place": event.place.rough_place()[0],
        "needs": event.needs(),
        "can_edit": can_edit,
        # What waits for the host's answer or was answered; who just comes is under "Who is coming"
        "offers": [match for match in matches if not match.is_coming] if can_edit else [],
        "coming": coming,
        "coming_people": sum(match.people for match in coming),
        "own_match": own_match,
        "takes_people": event.takes_people(request.user),
        "coming_form": ComingForm(event),
        "references": _references(event),
    })


def _references(event):
    """References written after anything that was part of the event: help offered on
    it, coming to it, or a stay at its community that brought one of its needs. In both
    directions: guests about the community, the ambassador about the guests."""
    from django.contrib.contenttypes.models import ContentType
    from gift_economy.references.models import Reference, ReferenceSkill, with_card_data

    matches = Match.objects.filter(
        Q(content_type=ContentType.objects.get_for_model(Event), object_id=str(event.pk))
        | Q(contributions__listing__event=event)
    )
    references = list(with_card_data(Reference.objects.filter(match__in=matches).distinct()))
    for reference in references:
        reference.about_other = True  # say who or what each one is about
        reference.visible_skill_tags = [t for t in reference.skill_tags.all() if t.status == ReferenceSkill.STATUS_CONFIRMED]
    return references


def _save_event(request, event, template_context):
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    formset = NeedFormSet(request.POST or None, instance=event, prefix="needs")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            event = form.save(commit=False)
            if not event.pk:
                event.created_by = request.user
            event.touch(save=False)
            event.save()
            form.save_skills_to_learn(event)
            formset.instance = event
            formset.save(commit=False)
            for need in formset.deleted_objects:
                need.delete()
            # Keep the needs in the order they were entered
            kept = [f for f in formset.forms if f.has_changed() or f.instance.pk]
            for order, need_form in enumerate(f for f in kept if f not in formset.deleted_forms):
                need = need_form.save(commit=False)
                need.event = event
                need.order = order
                need.save()
                need_form.save_category(need)
        messages.success(request, event.texts["saved"])
        return redirect(event.get_absolute_url())
    return render(request, "events/event_form.html", {
        **template_context, "form": form, "formset": formset, "texts": event.texts,
    })


@login_required
def create(request, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    event = Event(community=community)
    if request.GET.get("kind") in kinds.TEXTS:
        event.kind = request.GET["kind"]
    if not event.can_edit(request.user):
        raise PermissionDenied
    return _save_event(request, event, {"community": community})


@login_required
def edit(request, community_slug, slug):
    event = _event(community_slug, slug, Event.objects.select_related("community__owner"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    return _save_event(request, event, {"community": event.community, "event": event})


@login_required
@require_POST
def archive(request, community_slug, slug):
    event = _event(community_slug, slug, Event.objects.select_related("community__owner"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    event.archived_at = timezone.now()
    event.save(update_fields=["archived_at"])
    messages.success(request, event.texts["archived_by_you"])
    return redirect(event.community.get_absolute_url())


@login_required
@require_POST
def confirm(request, community_slug, slug):
    """The ambassador says the event is still current (also brings back an archived one
    that hasn't ended)."""
    event = _event(community_slug, slug, Event.objects.select_related("community__owner"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    if event.is_over:
        messages.error(request, event.texts["ended_change_dates"])
        return redirect(event.url("edit"))
    event.touch()
    messages.success(request, event.texts["confirmed"])
    return redirect(event.get_absolute_url())


def confirm_by_email(request, community_slug, slug, token):
    """One click from the "Is this still current?" email, no login needed."""
    event = _event(community_slug, slug, Event.objects.select_related("community"))
    try:
        pk = read_confirm_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid or expired link.")
    if pk != event.pk:
        return HttpResponseBadRequest("Invalid or expired link.")
    if event.is_over:
        messages.error(request, event.texts["ended_change_dates"])
    else:
        event.touch()
        messages.success(request, event.texts["confirmed"])
    return redirect(event.get_absolute_url())


@login_required
@require_POST
def toggle_need(request, community_slug, slug, need_pk):
    """Mark a need as covered (however it was covered), or open it again."""
    event = _event(community_slug, slug, Event.objects.select_related("community__owner"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    need = get_object_or_404(event.listings.filter(type=Listing.TYPE_WISH), pk=need_pk)
    need.covered_at = None if need.covered_at else timezone.now()
    need.save(update_fields=["covered_at"])
    event.touch()
    return redirect(event.get_absolute_url())


@login_required
def offer_help(request, community_slug, slug):
    event = _event(community_slug, slug)
    if not event.is_current or event.manager is None:
        messages.error(request, event.texts["no_offers"])
        return redirect(event.get_absolute_url())
    if request.user == event.manager:
        return redirect(event.get_absolute_url())

    form = HelpOfferForm(event, request.POST or None, preselected=request.GET.getlist("need"))
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            match = Match(from_user=request.user, recipient=event.get_match_owner(), message=form.cleaned_data["message"])
            match.target = event
            match.save()
            StayDetails.objects.create(
                match=match,
                volunteer_mode="wish",
                stay_from=_day_start(form.cleaned_data["stay_from"]),
                stay_to=_day_start(form.cleaned_data["stay_to"]),
            )
            for need, quantity in form.chosen_needs():
                Contribution.objects.create(listing=need, match=match, quantity=quantity)
        notify_match_created(match, http_request=request)
        messages.success(request, _("Your offer has been sent to %(community)s!") % {"community": event.community.name})
        return redirect(match.get_absolute_url())

    return render(request, "events/offer_help.html", {
        "event": event, "community": event.community, "form": form,
    })


@login_required
@require_POST
def come(request, community_slug, slug):
    """"I'm coming" on an open event: a match that is accepted at once, with the days
    and the number of people. Nobody has to answer it, and the host gets no message per
    person: they see who comes on the event's page and in their calendar."""
    event = _event(community_slug, slug)
    if not (event.is_open and event.takes_people(request.user)):
        messages.error(request, event.texts["no_offers"])
        return redirect(event.get_absolute_url())
    form = ComingForm(event, request.POST)
    if not form.is_valid():
        messages.error(request, _("Please check how many you are and the days."))
        return redirect(event.get_absolute_url())
    stay_from, stay_to = form.days()
    with transaction.atomic():
        own = event.matches.filter(from_user=request.user).exclude(status__in=Match.CLOSED_STATUSES)
        if not own.exists():
            match = Match(
                from_user=request.user, recipient=event.get_match_owner(), message="",
                status=Match.STATUS_ACCEPTED, responded_at=timezone.now(),
            )
            match.target = event
            match.save()
            StayDetails.objects.create(
                match=match, volunteer_mode=StayDetails.MODE_COME, people=form.cleaned_data["people"],
                stay_from=_day_start(stay_from), stay_to=_day_start(stay_to),
            )
    messages.success(request, _("Great, you are on the list!"))
    return redirect(event.get_absolute_url())


@login_required
@require_POST
def not_coming(request, community_slug, slug):
    """Take "I'm coming" back."""
    event = _event(community_slug, slug)
    own = event.matches.filter(from_user=request.user, stay_details__volunteer_mode=StayDetails.MODE_COME)
    if own.exists():
        own.delete()
        messages.success(request, _("You are off the list."))
    return redirect(event.get_absolute_url())


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None
