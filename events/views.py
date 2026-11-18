import html
from collections import Counter
from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _, ngettext
from django.views.decorators.http import require_POST

from communities.models import Community
from dashboard_lists import Choice, paginate, query_url
from gift_economy.matches.emails import notify_match_created
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match, StayDetails, create_stay, joining_q
from gift_economy.gifts.skills.models import Skill, skill_name_q

from . import kinds
from .forms import AskToJoinForm, ComingForm, EventForm, HelpOfferForm, NeedForm, NeedFormSet
from .filters import EventFilters, going_to
from .freshness import read_confirm_token
from .models import Event
from .signals import asked_to_join, coming, event_created

# An event's needs and skills to learn, with how far each is covered
_LISTINGS = Prefetch(
    "listings", queryset=Listing.objects.select_related("skill").prefetch_related(
        "categories", "contributions__match__from_user",
    ),
)


def _events():
    return Event.objects.select_related(
        "community", "community__ambassador", "host_user", "host_tour__organiser",
    ).prefetch_related(_LISTINGS, "community__photos")


def _event(slug, community_slug=None, kind=None, events=None):
    """The event at an address: under its kind's own one (`kind`), else under its
    community's."""
    events = _events() if events is None else events
    if kind:
        return get_object_or_404(events, kind=kind, slug=slug)
    events = events.exclude(kind__in=list(kinds.ADDRESSES))
    return get_object_or_404(events, community__slug=community_slug, slug=slug)


def event_list(request):
    """Events on a map, the list in a modal, with a search and filters (EventFilters),
    as on the communities. The map starts on the whole world, or around where one asked
    (?near=)."""
    user = request.user
    filters = EventFilters(request.GET, user)
    return render(request, "events/event_list.html", {
        "filters": filters,
        "countries": _countries(filters),
        "kind_choices": [(value, kinds.TEXTS[value]["plural"], kinds.ICONS[value]) for value, _label in kinds.CHOICES],
        "need_choices": [(value, label) for value, label in NeedForm.KIND_CHOICES],
        "flag_choices": _flag_choices(user),
        "create_buttons": _create_buttons(user),
        "home": filters.near,
        "radius": user.match_radius if user.is_authenticated else None,
    })


@login_required
def going(request):
    """The events one comes to, hosts or whose help was accepted, as cards in the dashboard:
    those not over yet, the soonest first, or the past ones, the latest first."""
    past = request.GET.get("when") == "past"
    user = request.user
    # Asking to join one, not answered yet: on the list, with the conversation
    open_statuses = (Match.STATUS_PENDING, Match.STATUS_COUNTER)
    asked = {
        int(match.object_id): match
        for match in Match.objects.filter(joining_q(), from_user=user, status__in=open_statuses)
    }
    # Also those one hosts oneself, or with one's tour
    mine = _events().filter(
        Q(pk__in=going_to(user)) | Q(pk__in=list(asked)) | Q(host_user=user) | Q(host_tour__organiser=user)
    )
    today = timezone.localdate()
    upcoming = mine.current().order_by(F("starts_on").asc(nulls_first=True), F("ends_on").asc(nulls_last=True))
    over = mine.filter(ends_on__lt=today).order_by("-ends_on", "-starts_on")
    page = paginate(request, over if past else upcoming)
    # What waits for one's answer where people ask to join one's own
    waiting = Counter(
        int(pk) for pk in Match.objects.filter(joining_q(), recipient=user, status=Match.STATUS_PENDING)
        .values_list("object_id", flat=True)
    )
    for event in page:
        event.own_request = asked.get(event.pk)
        event.waiting_answers = waiting.get(event.pk, 0)
    return render(request, "events/going.html", {
        "page": page,
        "past": past,
        "create_buttons": _create_buttons(user),
        "whens": [
            Choice(_("Upcoming"), query_url(request, when=None), active=not past, count=upcoming.count()),
            Choice(_("Past"), query_url(request, when="past"), active=past, count=over.count()),
        ],
    })


def _create_buttons(user):
    """(url, what the button says, icon) for "add an event": the kinds one may host
    oneself, and those of the communities one is a member of, named after the community
    when there are several."""
    if not user.is_authenticated:
        return []
    buttons = [
        (reverse(f"events:{kind}_create"), label, icon) for kind, label, icon in kinds.event_kind_buttons(kinds.HOST_PERSON)
    ]
    own = {kind for kind, _label in kinds.choices_for(kinds.HOST_PERSON)}
    communities = list(user.member_communities_qs().order_by("name"))
    for kind, label, icon in kinds.event_kind_buttons(kinds.HOST_COMMUNITY):
        if kind in own:
            continue
        for community in communities:
            url = f"{reverse('events:create', args=[community.slug])}?kind={kind}"
            buttons.append((url, f"{label} ({community.name})" if len(communities) > 1 else label, icon))
    return buttons


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
        glyph, colour = event.kind_pin
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

    events = filters.base(Event.objects.all())
    codes = set(events.values_list("community__country", flat=True)) | set(events.values_list("country", flat=True))
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


def detail(request, slug, community_slug=None, kind=None):
    event = _event(slug, community_slug, kind)
    can_edit = event.can_edit(request.user)
    if event.archived_at and not can_edit:
        messages.info(request, event.texts["archived"])
    matches = list(
        event.matches.select_related("from_user", "stay_details")
        .prefetch_related("contributions__listing__skill").exclude(status__in=Match.CLOSED_STATUSES)
    )
    coming = [match for match in matches if match.status == Match.STATUS_ACCEPTED]
    guests = list(event.guests.coming())
    own_match = None
    if request.user.is_authenticated:
        own_match = next((match for match in matches if match.from_user == request.user), None)
    return render(request, "events/event_detail.html", {
        "event": event,
        "community": event.community,
        "place": event.place_for(request.user)[0],
        "needs": event.needs(),
        "can_edit": can_edit,
        # Its community's calendar is the ambassador's
        "is_ambassador": bool(event.community_id and event.community.is_ambassador(request.user)),
        # What waits for the host's answer or was answered; who just comes is under "Who is
        # coming", and so is who was accepted where people ask to join
        "offers": [
            match for match in matches
            if not match.is_coming and not (event.asks_to_join and match.status == Match.STATUS_ACCEPTED)
        ] if can_edit else [],
        "coming": coming,
        "guests": guests,
        "coming_people": sum(match.people for match in coming) + sum(guest.people for guest in guests),
        "own_match": own_match,
        # Said "I'm coming", or was accepted where people ask to join
        "own_coming": bool(
            own_match and own_match.status == Match.STATUS_ACCEPTED and (own_match.is_coming or event.asks_to_join)
        ),
        "takes_people": event.takes_people(request.user),
        "may_just_come": event.may_just_come(request.user),
        "coming_form": ComingForm(event),
        "coming_fields": kinds.COMING_FIELDS.get(event.kind),
        "guest_sign_up": kinds.GUEST_SIGN_UPS.get(event.kind),
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


def save_event(request, event, cancel_url, on_saved=None):
    """The event's form, and saving it with its needs. `on_saved(event)` runs in the same
    transaction after the event is saved (e.g. a tour's stop pointing at it)."""
    editing = bool(event.pk)
    form = EventForm(request.POST or None, request.FILES or None, instance=event)
    formset = NeedFormSet(request.POST or None, instance=event, prefix="needs") if event.takes_needs else None
    if request.method == "POST" and form.is_valid() and (formset is None or formset.is_valid()):
        with transaction.atomic():
            event = form.save(commit=False)
            if not event.pk:
                event.created_by = request.user
            event.touch(save=False)
            event.save()
            if formset is not None:
                form.save_skills_to_learn(event)
                _save_needs(event, formset)
            if on_saved is not None:
                on_saved(event)
            if not editing:
                event_created.send(sender=Event, event=event, user=request.user)
        messages.success(request, event.texts["saved"])
        return redirect(event.get_absolute_url())
    return render(request, "events/event_form.html", {
        "event": event, "editing": editing, "form": form, "formset": formset, "texts": event.texts,
        "cancel_url": event.get_absolute_url() if editing else cancel_url,
    })


def _save_needs(event, formset):
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


@login_required
def create(request, community_slug=None, kind=None):
    """A new event: a community's (?kind= one of those it may host), or one of a kind
    with its own address, which the person who starts it hosts."""
    if community_slug:
        community = get_object_or_404(Community, slug=community_slug)
        event = Event(community=community)
        if request.GET.get("kind") in dict(kinds.choices_for(kinds.HOST_COMMUNITY)):
            event.kind = request.GET["kind"]
        cancel_url = community.get_absolute_url()
    else:
        if kinds.HOST_PERSON not in kinds.HOSTS[kind]:
            raise PermissionDenied
        event = Event(kind=kind, host_user=request.user)
        cancel_url = reverse("events:list")
    if not event.can_edit(request.user):
        raise PermissionDenied
    return save_event(request, event, cancel_url)


@login_required
def edit(request, slug, community_slug=None, kind=None):
    event = _event(slug, community_slug, kind, Event.objects.select_related("community__ambassador", "host_user", "host_tour"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    return save_event(request, event, event.get_absolute_url())


@login_required
@require_POST
def delete(request, slug, community_slug=None, kind=None):
    """Whoever may edit an event deletes it, with who comes and the conversations about
    it; references written about it stay. Nothing is deleted on its own: past events are
    archived."""
    event = _event(slug, community_slug, kind, Event.objects.select_related("community__ambassador", "host_user", "host_tour"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    host_url = event.host.get_absolute_url()
    event.delete()
    messages.success(request, _("“%(title)s” is deleted.") % {"title": event.title})
    return redirect(host_url)


@login_required
@require_POST
def archive(request, slug, community_slug=None, kind=None):
    event = _event(slug, community_slug, kind, Event.objects.select_related("community__ambassador", "host_user", "host_tour"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    event.archived_at = timezone.now()
    event.save(update_fields=["archived_at"])
    messages.success(request, event.texts["archived_by_you"])
    return redirect(event.host.get_absolute_url())


@login_required
@require_POST
def confirm(request, slug, community_slug=None, kind=None):
    """The ambassador says the event is still current (also brings back an archived one
    that hasn't ended)."""
    event = _event(slug, community_slug, kind, Event.objects.select_related("community__ambassador", "host_user", "host_tour"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    if event.is_over:
        messages.error(request, event.texts["ended_change_dates"])
        return redirect(event.url("edit"))
    event.touch()
    messages.success(request, event.texts["confirmed"])
    return redirect(event.get_absolute_url())


def confirm_by_email(request, slug, token, community_slug=None, kind=None):
    """One click from the "Is this still current?" email, no login needed."""
    event = _event(slug, community_slug, kind, Event.objects.select_related("community", "host_user", "host_tour"))
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
def toggle_need(request, slug, need_pk, community_slug=None, kind=None):
    """Mark a need as covered (however it was covered), or open it again."""
    event = _event(slug, community_slug, kind, Event.objects.select_related("community__ambassador", "host_user", "host_tour"))
    if not event.can_edit(request.user):
        raise PermissionDenied
    need = get_object_or_404(event.listings.filter(type=Listing.TYPE_WISH), pk=need_pk)
    need.covered_at = None if need.covered_at else timezone.now()
    need.save(update_fields=["covered_at"])
    event.touch()
    return redirect(event.get_absolute_url())


@login_required
def offer_help(request, slug, community_slug=None, kind=None):
    event = _event(slug, community_slug, kind)
    if event.asks_to_join:
        return redirect(event.url("ask_to_join"))
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
        messages.success(request, _("Your offer has been sent to %(community)s!") % {"community": event.host_name})
        return redirect(match.get_absolute_url())

    return render(request, "events/offer_help.html", {
        "event": event, "community": event.community, "form": form,
    })


@login_required
def ask_to_join(request, slug, community_slug=None, kind=None):
    """Asking to join an event that needs nothing but people and isn't open: how many and
    a few words, no days. The host accepts or declines in the match's conversation;
    accepted, they come."""
    event = _event(slug, community_slug, kind)
    if not event.asks_to_join:
        return redirect(event.url("offer_help"))
    if event.may_just_come(request.user) or not event.takes_people(request.user):
        return redirect(event.get_absolute_url())
    own = event.matches.filter(from_user=request.user).exclude(status__in=Match.CLOSED_STATUSES).first()
    if own is not None:
        return redirect(own.get_absolute_url())
    form = AskToJoinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        day = _day_start(event.starts_on)
        with transaction.atomic():
            match = create_stay(
                request.user, event, message=form.cleaned_data["message"], people=form.cleaned_data["people"],
                stay_from=day, stay_to=_day_start(event.ends_on) or day,
            )
            asked_to_join.send(sender=Event, event=event, user=request.user, match=match, data=request.POST)
        notify_match_created(match, http_request=request)
        messages.success(request, _("Your request has been sent to %(host)s!") % {"host": event.host_name})
        return redirect(match.get_absolute_url())
    return render(request, "events/ask_to_join.html", {
        "event": event, "form": form, "coming_fields": kinds.COMING_FIELDS.get(event.kind),
    })


@login_required
@require_POST
def come(request, slug, community_slug=None, kind=None):
    """"I'm coming" on an open event (or one's own tour's): a match that is accepted at
    once, with the days and the number of people. Nobody has to answer it, and the host
    gets no message per person: they see who comes on the event's page and in their
    calendar."""
    event = _event(slug, community_slug, kind)
    if not (event.may_just_come(request.user) and event.takes_people(request.user)):
        messages.error(request, event.texts["no_offers"])
        return redirect(event.get_absolute_url())
    form = ComingForm(event, request.POST)
    if not form.is_valid():
        messages.error(request, _("Please check how many you are and the days."))
        return redirect(event.get_absolute_url())
    free = event.free_places()
    if free is not None and form.cleaned_data["people"] > free:
        messages.error(request, ngettext(
            "Only %(count)s more person can come.", "Only %(count)s more people can come.", free,
        ) % {"count": free})
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
            coming.send(sender=Event, event=event, user=request.user, match=match, data=request.POST)
    messages.success(request, _("Great, you are on the list!"))
    return redirect(event.get_absolute_url())


@login_required
@require_POST
def not_coming(request, slug, community_slug=None, kind=None):
    """Take "I'm coming" back."""
    event = _event(slug, community_slug, kind)
    own = event.matches.filter(from_user=request.user, stay_details__volunteer_mode=StayDetails.MODE_COME)
    if own.exists():
        own.delete()
        messages.success(request, _("You are off the list."))
    return redirect(event.get_absolute_url())


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None
