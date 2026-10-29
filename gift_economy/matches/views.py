from collections import Counter
from datetime import datetime as _dt

from django.contrib import messages as flash
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from django.views.decorators.http import require_POST

from dashboard_lists import Choice, paginate, query_url
from gift_economy.gifts.models import Listing

from .emails import notify_match_message, notify_match_response, read_action_token, read_suggestions_unsubscribe_token
from .forms import MatchMessageForm
from .models import STAY_APP_LABELS, Match, MatchMessage, Suggestion, loan_span

# What the matches page can show, by its "type" query param: gifts (things) and skills
# (and knowledge and helping hands) together on one page (with suggestions first),
# volunteer visits on their own.
_TYPES = {
    "gift": {"kinds": Listing.THING_KINDS, "title": _("Gifts"), "icon": "fa fa-gift"},
    "skills": {"kinds": Listing.SKILL_KINDS, "title": _("Skills"), "icon": "fa fa-graduation-cap"},
}
_VOLUNTEER = {
    "title": _("Volunteer Visits"), "icon": "fa-solid fa-campground", "empty": _("No volunteer visits yet."),
}

_OPEN = (Match.STATUS_PENDING, Match.STATUS_COUNTER)
_STATUS_FILTERS = {
    "open":     (pgettext_lazy("match status", "Open"), _OPEN),
    "accepted": (_("Accepted"), (Match.STATUS_ACCEPTED,)),
    "declined": (_("Declined"), (Match.STATUS_DECLINED,)),
    "all":      (_("All"), None),
}


def _with_details(matches):
    return matches.select_related("content_type", "from_user", "recipient").prefetch_related("target")


def _listing_matches(kinds=None):
    """Matches about an offer or a wish, of these kinds (all without)."""
    matches = Match.objects.filter(content_type__app_label="gifts")
    if kinds:
        matches = matches.filter(object_id__in=Listing.objects.filter(kind__in=kinds).values("pk"))
    return _with_details(matches)


def _stays():
    return _with_details(Match.objects.filter(content_type__app_label__in=STAY_APP_LABELS))


# ── Matches page ───────────────────────────────────────────────────────────────

@login_required
def matches_list(request):
    """Gifts and skills on one page: first the suggestions (what fits their wishes, offers
    and skills; a match once someone asks), then the requests received and sent, all
    filtered by ?type=gift|skills. ?type=volunteer: the volunteer visits, on their own."""
    kind = request.GET.get("type", "")
    if kind == "volunteer":
        return _volunteer_visits(request)
    if kind not in _TYPES:
        kind = ""
    user = request.user
    kinds = _TYPES[kind]["kinds"] if kind else None

    suggestions = _suggestions_of(user)
    if kind:
        suggestions = suggestions.filter(kind=kind)
    boxes = {
        "received": _listing_matches(kinds).filter(recipient=user),
        "sent":     _listing_matches(kinds).filter(from_user=user),
    }
    counts = {"suggestions": suggestions.count(), **{key: matches.count() for key, matches in boxes.items()}}
    # New suggestions; requests to answer (the owner answers a request, the requester a
    # counter-proposal)
    waiting = {
        "suggestions": suggestions.filter(seen_at=None).count(),
        "received":    boxes["received"].filter(status=Match.STATUS_PENDING).count(),
        "sent":        boxes["sent"].filter(status=Match.STATUS_COUNTER).count(),
    }
    box = request.GET.get("box")
    if box not in counts:
        box = "suggestions"
    tabs = [
        Choice(label, query_url(request, box=key, status=None), key == box, counts[key], waiting[key])
        for key, label in (("suggestions", _("Suggestions")), ("received", _("Requests to you")), ("sent", _("Your requests")))
    ]
    types = [
        Choice(label, query_url(request, type=key or None, status=None), key == kind)
        for key, label in (("", _("All")), ("gift", _("Gifts")), ("skills", _("Skills")))
    ]
    context = {"request_type": kind, "types": types, "tabs": tabs, "box": box}

    if box == "suggestions":
        page = paginate(request, suggestions)
        shown = _shown(page.object_list)
        return render(request, "matches/matches_list.html", {
            **context, "page": page, "suggestions": shown, "new_ids": _mark_seen(user, shown),
        })
    return render(request, "matches/matches_list.html", {
        **context, **_requests(request, boxes[box]), "show_from": box == "received",
        "empty": _("No requests yet."),
    })


def _requests(request, matches):
    """A page of matches filtered by status, with the status filters."""
    by_status = dict(matches.order_by().values_list("status").annotate(n=Count("pk")))
    status = request.GET.get("status")
    if status not in _STATUS_FILTERS:
        status = "open" if any(by_status.get(s) for s in _OPEN) else "all"
    filters = [
        Choice(
            label, query_url(request, status=key), key == status,
            sum(by_status.values()) if statuses is None else sum(by_status.get(s, 0) for s in statuses),
        )
        for key, (label, statuses) in _STATUS_FILTERS.items()
    ]
    statuses = _STATUS_FILTERS[status][1]
    if statuses is not None:
        matches = matches.filter(status__in=statuses)
    return {"filters": filters if by_status else [], "page": paginate(request, matches)}


def _volunteer_visits(request):
    """Volunteer stays and help with projects, received and sent. Only ambassadors
    receive them, so the others (who never did) see just their own requests."""
    user = request.user
    boxes = {
        "received": _stays().filter(recipient=user),
        "sent":     _stays().filter(from_user=user),
    }
    if not user.communities.exists() and not boxes["received"].exists():
        del boxes["received"]
    # The owner answers a request, the requester a counter-proposal
    answers = {"received": Match.STATUS_PENDING, "sent": Match.STATUS_COUNTER}
    waiting = {key: matches.filter(status=answers[key]).count() for key, matches in boxes.items()}
    counts = {key: matches.count() for key, matches in boxes.items()}
    box = request.GET.get("box")
    if box not in boxes:
        # Open on the tab that needs you, otherwise on the one that has anything
        box = next((key for key in boxes if waiting[key]), None) \
            or next((key for key in boxes if counts[key]), next(iter(boxes)))
    tabs = [
        Choice(label, query_url(request, box=key, status=None), key == box, counts[key], waiting[key])
        for key, label in (("received", _("Requests to you")), ("sent", _("Your requests")))
        if key in boxes
    ]
    return render(request, "matches/matches_list.html", {
        "request_type": "volunteer", "kind": _VOLUNTEER, "tabs": tabs, "box": box,
        **_requests(request, boxes[box]), "show_from": box == "received", "empty": _VOLUNTEER["empty"],
    })


# ── Match detail ────────────────────────────────────────────────────────────────

def _parse_loan(data):
    """(start, end) of the days, or hours, a counter-proposal suggests for a loan; None if
    there is no first day, or it would come back before it is borrowed."""
    from datetime import date, time
    def parse(kind, raw):
        try:
            return kind.fromisoformat(raw) if raw else None
        except ValueError:
            return None
    first = parse(date, data.get("counter_stay_from", ""))
    if first is None:
        return None
    starts_at, ends_at = loan_span(
        first, parse(date, data.get("counter_stay_to", "")),
        parse(time, data.get("counter_from_time", "")), parse(time, data.get("counter_to_time", "")),
    )
    return (starts_at, ends_at) if ends_at > starts_at else None


def _parse_day(raw):
    """A day from a date input, as an aware datetime at its start; None if blank or invalid."""
    try:
        day = _dt.fromisoformat(raw) if raw else None
    except ValueError:
        return None
    return timezone.make_aware(day) if day and timezone.is_naive(day) else day


@login_required
def match_detail(request, pk):
    match = get_object_or_404(
        Match.objects.select_related("content_type", "from_user", "recipient"), pk=pk
    )
    target = match.target
    if target is None:
        raise Http404

    # Only the two sides act on a match; staff may open it too
    is_party = request.user in (match.from_user, match.recipient)
    if not (is_party or request.user.is_staff):
        raise Http404
    if request.method == "POST" and not is_party:
        raise PermissionDenied

    is_owner     = request.user == match.recipient
    is_requester = request.user == match.from_user

    thread = list(match.thread.select_related("sender").all())
    latest_status_msg  = None
    latest_counter_msg = None
    for msg in reversed(thread):
        if msg.status_to and latest_status_msg is None:
            latest_status_msg = msg
        if msg.status_to == Match.STATUS_COUNTER and latest_counter_msg is None:
            latest_counter_msg = msg
        if latest_status_msg and latest_counter_msg:
            break

    counter_by_owner = (
        match.status == Match.STATUS_COUNTER
        and latest_status_msg is not None
        and match.recipient_id is not None
        and latest_status_msg.sender_id == match.recipient_id
    )
    owner_can_decide     = is_owner and not counter_by_owner
    requester_can_decide = is_requester and counter_by_owner

    if request.method == "POST":
        action = request.POST.get("action", "message")

        if action == "message":
            body = request.POST.get("body", "").strip()
            if body:
                MatchMessage.objects.create(match=match, sender=request.user, body=body)
                notify_match_message(match, sender=request.user, message=body, http_request=request)
            return redirect(match.get_absolute_url())

        if action == "extras" and is_party:
            # Ask for more of the other side's gifts and skills as part of this exchange
            other = match.recipient if is_requester else match.from_user
            options = {
                option.pk: option
                for option in (Listing.objects.of(other).filter(type=Listing.TYPE_OFFER).select_related("skill") if other else [])
            }
            options.pop(match.object_id, None)  # what the exchange is about stays part of it
            asked = [options[pk] for pk in request.POST.getlist("listing") if pk in options]
            had = set(match.listings.values_list("pk", flat=True))
            new = [option for option in asked if option.pk not in had]
            match.listings.remove(*[pk for pk in had if pk in options and options[pk] not in asked])
            match.listings.add(*asked)
            if new:
                body = _("Also asked for: %(things)s") % {"things": ", ".join(option.display_title for option in new)}
                MatchMessage.objects.create(match=match, sender=request.user, body=body)
                notify_match_message(match, sender=request.user, message=body, http_request=request)
            flash.success(request, _("Saved what is part of this exchange."))
            return redirect(f"{match.get_absolute_url()}#person")

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {"accept": Match.STATUS_ACCEPTED, "decline": Match.STATUS_DECLINED}[action]
            if new_status == Match.STATUS_ACCEPTED and match.is_loan:
                # The agreed time is the loan's from now on; a tool is lent once at a time
                starts_at, ends_at = match.loan_period()
                if target.lends_out and not target.is_free(starts_at, ends_at, exclude_match=match):
                    flash.error(request, _("It is already lent on some of these days. Propose other days instead."))
                    return redirect(match.get_absolute_url())
                match.loan.starts_at, match.loan.ends_at = starts_at, ends_at
                match.loan.save()
            body = request.POST.get("body", "").strip()
            MatchMessage.objects.create(match=match, sender=request.user, body=body, status_to=new_status)
            match.status       = new_status
            match.responded_at = timezone.now()
            match.save()
            notify_match_response(match, actor=request.user, http_request=request, message=body)
            flash.success(request, _("Response sent."))
            return redirect(match.get_absolute_url())

        if action == "counter" and is_owner:
            msg = MatchMessage(
                match=match, sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=Match.STATUS_COUNTER,
            )
            if match.is_community_stay:
                # The stay is at the community, so only the dates can change.
                msg.counter_stay_from = _parse_day(request.POST.get("counter_stay_from", ""))
                msg.counter_stay_to   = _parse_day(request.POST.get("counter_stay_to", ""))
                if not (msg.counter_stay_from or msg.counter_stay_to):
                    flash.error(request, _("Please suggest when the stay could start or end."))
                    return redirect(match.get_absolute_url())
                if msg.counter_stay_from and msg.counter_stay_to and msg.counter_stay_to < msg.counter_stay_from:
                    flash.error(request, _("The stay can't end before it starts."))
                    return redirect(match.get_absolute_url())
            else:
                if match.is_loan:
                    # Other days or hours to borrow it, and maybe another place to pick it up
                    span = _parse_loan(request.POST)
                    if span is None:
                        flash.error(request, _("It can't come back before it is borrowed."))
                        return redirect(match.get_absolute_url())
                    msg.counter_stay_from, msg.counter_stay_to = span
                msg.counter_location_type = request.POST.get("counter_location_type", "")
                msg.counter_location      = request.POST.get("counter_location", "")
                try:
                    msg.counter_lat = float(request.POST.get("counter_lat") or "")
                except (ValueError, TypeError):
                    msg.counter_lat = None
                try:
                    msg.counter_lon = float(request.POST.get("counter_lon") or "")
                except (ValueError, TypeError):
                    msg.counter_lon = None
                raw_dt = request.POST.get("counter_date", "")
                try:
                    msg.counter_date = _dt.fromisoformat(raw_dt) if raw_dt else None
                except ValueError:
                    msg.counter_date = None
            msg.save()
            match.status       = Match.STATUS_COUNTER
            match.responded_at = timezone.now()
            match.save()
            notify_match_response(match, actor=request.user, http_request=request, message=msg.body, counter=msg)
            flash.success(request, _("Counter-proposal sent."))
            return redirect(match.get_absolute_url())

    return render(request, "matches/match_detail.html", {
        "match":                match,
        # Volunteer visits have their own place in the sidebar and breadcrumb
        "request_type":         "volunteer" if match.is_community_stay else "",
        "target":               target,
        "is_owner":             is_owner,
        "is_requester":         is_requester,
        "is_party":             is_party,
        "thread":               thread,
        "latest_status_msg":    latest_status_msg,
        "latest_counter_msg":   latest_counter_msg,
        "owner_can_decide":     owner_can_decide,
        "requester_can_decide": requester_can_decide,
        "message_form":         MatchMessageForm(),
        "loc_choices":          Match.LOC_CHOICES,
        "person":               _person(match.recipient if is_requester else match.from_user),
        "asked_listing_ids":    {listing.pk for listing in match.listings.all()},
    })


def _person(user):
    """What the other side brings: their skills (with level and how many references), the
    gifts they offer (they might bring them along) and the communities they look after."""
    if user is None:
        return None
    from django.contrib.contenttypes.models import ContentType
    from gift_economy.references.models import Reference

    offers = Listing.objects.of(user).filter(type=Listing.TYPE_OFFER).select_related("skill")
    skills = sorted(offers.filter(kind=Listing.KIND_SKILL), key=lambda listing: listing.display_title)
    references = Counter(Reference.objects.filter(
        content_type=ContentType.objects.get_for_model(Listing),
        object_id__in=[str(skill.pk) for skill in skills],
    ).values_list("object_id", flat=True))
    for skill in skills:
        skill.reference_count = references[str(skill.pk)]
    return {
        "user": user,
        "skills": skills,
        "offers": list(offers.exclude(kind=Listing.KIND_SKILL).order_by("-updated_at")),
        "communities": list(user.communities.order_by("name")),
    }


# ── Email token action (no login required) ────────────────────────────────────

def email_action(request, token):
    """Accept or decline any match via signed link in email — no login required."""
    try:
        payload = read_action_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid or expired link.")

    match  = get_object_or_404(Match, pk=payload["id"])
    action = payload["action"]

    if match.status != Match.STATUS_PENDING:
        flash.info(request, _("This interest has already been responded to."))
        return redirect(match.get_absolute_url())

    target = match.target
    if action == "accept" and match.is_loan and target is not None and target.lends_out and not target.is_free(
        match.loan.starts_at, match.loan.ends_at, exclude_match=match,
    ):
        flash.error(request, _("It is already lent on some of these days. Propose other days instead."))
        return redirect(match.get_absolute_url())

    actor = match.recipient
    match.status       = Match.STATUS_ACCEPTED if action == "accept" else Match.STATUS_DECLINED
    match.responded_at = timezone.now()
    match.save(update_fields=["status", "responded_at"])
    MatchMessage.objects.create(match=match, sender=actor, body="", status_to=match.status)
    notify_match_response(match, actor=actor, http_request=request)

    return render(request, "matches/email_action_done.html", {
        "action": action,
        "title": match.target.get_match_display_name() if match.target else "",
        "detail_url": match.get_absolute_url(),
    })


# ── Suggestions ────────────────────────────────────────────────────────────────

def _suggestions_of(user):
    return (
        user.suggestions.filter(dismissed_at=None)
        .select_related("own_type", "other_type", "other_user")
        .prefetch_related("own", "other")
    )


def _shown(suggestions):
    # Things deleted since are left out (their suggestions go with them, this is a safety net)
    return [s for s in suggestions if s.other is not None and s.own is not None]


def _mark_seen(user, shown):
    """Mark the shown suggestions as seen; returns the ids of those that were new."""
    new_ids = {s.pk for s in shown if s.seen_at is None}
    user.suggestions.filter(pk__in=new_ids).update(seen_at=timezone.now())
    return new_ids


@login_required
@require_POST
def dismiss_suggestion(request, pk):
    suggestion = get_object_or_404(Suggestion, pk=pk, user=request.user)
    suggestion.dismissed_at = timezone.now()
    suggestion.save(update_fields=["dismissed_at"])
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}) and next_url.startswith(reverse("matches:list")):
        return redirect(next_url)
    return redirect("matches:list")


def suggestions_unsubscribe(request, token):
    """One click from the weekly email turns it off, no login needed."""
    try:
        pk = read_suggestions_unsubscribe_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid link.")
    get_user_model().objects.filter(pk=pk).update(match_emails=False)
    flash.success(request, _(
        "You won't get emails about suggestions any more. You can turn them on again in your profile."
    ))
    return redirect("homepage:homepage")
