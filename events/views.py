import html
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from communities.models import Community
from dashboard_lists import paginate
from gift_economy.matches.emails import notify_match_created
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match, StayDetails, create_stay
from gift_economy.gifts.skills.models import Skill, skill_name_q

from . import kinds
from .forms import ComingForm, EventForm, HelpOfferForm, NeedForm, NeedFormSet
from .filters import EventFilters
from .freshness import read_confirm_token
from .models import Event

# An event's needs and skills to learn, with how far each is covered
_LISTINGS = Prefetch(
    "listings", queryset=Listing.objects.select_related("skill").prefetch_related(
        "categories", "contributions__match__from_user",
    ),
)


def _events():
    return Event.objects.select_related("community", "community__owner").prefetch_related(_LISTINGS, "community__photos")


def _event(community_slug, slug, events=None):
    return get_object_or_404(_events() if events is None else events, community__slug=community_slug, slug=slug)


def event_list(request):
    """Events on a map, the list in a modal, with a search and filters (EventFilters),
    as on the communities. The map starts around where one asked (?near=) or the place in
    one's profile."""
    user = request.user
    filters = EventFilters(request.GET, user)
    home = filters.near or (user.location if user.is_authenticated else None)
    return render(request, "events/event_list.html", {
        "filters": filters,
        "countries": _countries(filters),
        "kind_choices": [(value, kinds.TEXTS[value]["plural"], kinds.ICONS[value]) for value, _label in kinds.CHOICES],
        "need_choices": [(value, label) for value, label in NeedForm.KIND_CHOICES],
        "flag_choices": _flag_choices(user),
        "home": home,
        "radius": user.match_radius if user.is_authenticated else None,
    })


def _flag_choices(user):
    """The filters one switches on: (name, label, icon)."""
    flags = [
        ("room", _("Still has room"), "fa-users"), ("open", _("Just come"), "fa-door-open"),
        ("food", _("Food provided"), "fa-utensils"), ("bed", _("Bed provided"), "fa-bed"),
    ]
    if user.is_authenticated:
        flags += [("fits", _("Fits my skills"), "fa-hands-helping"), ("going", _("Going to"), "fa-calendar-check")]
    return flags


def api_list(request):
    """The list in the modal, for htmx: the events of the filters, nearest where one
    asked (or the place in one's profile) first."""
    user = request.user
    filters = EventFilters(request.GET, user)
    home = user.location if user.is_authenticated else None
    events = filters.order(list(filters.apply(filters.base(_events()))), home)
    page = paginate(request, events)
    return render(request, "events/_results.html", {"page": page, "events": page.object_list, "filters": filters})


def api_markers(request):
    """GeoJSON of the events of the filters in the map's visible area (bbox), where
    everyone sees them, with what their popup shows."""
    filters = EventFilters(request.GET, request.user)
    features = []
    for event in filters.in_view(filters.apply(filters.base(_events()))):
        glyph, colour = kinds.PINS.get(event.kind, kinds.PINS[kinds.COMMUNITY_EVENT])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [event.point.x, event.point.y]},
            "properties": {
                "title": event.title,
                "url": event.get_absolute_url(),
                "kind": event.kind_label,
                "kind_icon": event.kind_icon,
                "glyph": glyph,
                "colour": colour,
                # As text: the popup sets it as such
                "dates": " ".join(html.unescape(strip_tags(render_to_string("events/_event_dates.html", {"event": event}))).split()),
                "description": Truncator(event.description).chars(150),
                # Its host as on its card, with the avatar; where it is, the map shows
                "host": render_to_string("events/_host.html", {"event": event, "without_place": True}),
                "image": event.image.url if event.image else "",
                "learn": [skill.display_title for skill in event.skills_to_learn()][:5],
                "needs": [need.display_title for need in event.open_needs()][:5],
                "open": event.is_open,
                "food": event.food_provided,
                "bed": event.bed_provided,
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features})


def _countries(filters):
    """The countries with events of the time asked for, by name: (code, name)."""
    from django_countries import countries

    codes = set(filters.base(Event.objects.all()).values_list("community__country", flat=True))
    return sorted(((code, countries.name(code)) for code in codes if code and countries.name(code)), key=lambda pair: pair[1])


def api_suggest(request):
    """Suggestions for the search, from the events of the time asked for: their titles,
    their hosts, the skills one can learn or is needed for, and where they are."""
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    events = EventFilters(request.GET).base(Event.objects.all())
    suggestions, seen = [], set()

    def add(value, kind):
        if value and value.lower() not in seen and len(suggestions) < 10:
            seen.add(value.lower())
            suggestions.append({"value": value, "type": kind})

    for title in events.filter(title__icontains=q).values_list("title", flat=True)[:4]:
        add(title, "event")
    for name in events.filter(community__name__icontains=q).values_list("community__name", flat=True).distinct()[:3]:
        add(name, "community")
    listings = Listing.objects.filter(event__in=events, skill__isnull=False)
    for skill in Skill.objects.filter(skill_name_q(q, ""), listings__in=listings).distinct()[:4]:
        add(skill.get_name(), "skill")
    for name in events.filter(community__location_name__icontains=q).values_list("community__location_name", flat=True).distinct()[:3]:
        add(name, "location")
    return JsonResponse(suggestions, safe=False)


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
            match = create_stay(
                request.user, event, message=form.cleaned_data["message"], volunteer_mode="wish",
                stay_from=_day_start(form.cleaned_data["stay_from"]),
                stay_to=_day_start(form.cleaned_data["stay_to"]),
                contributions=form.chosen_needs(),
            )
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
