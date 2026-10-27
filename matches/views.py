from datetime import datetime as _dt

from django.contrib import messages as flash
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Count, Q
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from django.views.decorators.http import require_POST

from dashboard_lists import Choice, paginate, query_url

from .emails import notify_match_message, notify_match_response, read_action_token, read_suggestions_unsubscribe_token
from .forms import MatchMessageForm
from .models import STAY_APP_LABELS, Match, MatchMessage, Suggestion, suggestions_of_kind

# The kinds of match, by the list view's "type" query param. Kept as gifts/skills/
# communities/projects app labels rather than importing their models — matches never needs to
# import a domain app to work with a Match generically.
_KINDS = {
    "gift": {
        "app_labels": ("gifts",), "title": _("Gifts"), "icon": "fa fa-gift",
        "empty": _("No gift offers yet."),
    },
    "skills": {
        "app_labels": ("skills",), "title": _("Skills"), "icon": "fa fa-graduation-cap",
        "empty": _("No skill offers yet."),
    },
    "volunteer": {
        "app_labels": STAY_APP_LABELS, "title": _("Volunteer Visits"), "icon": "fa-solid fa-campground",
        "empty": _("No volunteer visits yet."),
    },
}

_OPEN = (Match.STATUS_PENDING, Match.STATUS_COUNTER)
_STATUS_FILTERS = {
    "open":     (pgettext_lazy("match status", "Open"), _OPEN),
    "accepted": (_("Accepted"), (Match.STATUS_ACCEPTED,)),
    "declined": (_("Declined"), (Match.STATUS_DECLINED,)),
    "all":      (_("All"), None),
}

# How many open matches of each kind the overview shows before linking to the full list
_OVERVIEW_ROWS = 5


def _matches_of(kind):
    return (
        Match.objects
        .filter(content_type__app_label__in=_KINDS[kind]["app_labels"])
        .select_related("content_type", "from_user", "recipient")
        .prefetch_related("target")
    )


# ── Matches lists ──────────────────────────────────────────────────────────────

@login_required
def matches_list(request):
    """One kind of match (?type=gift|skills|volunteer): received and sent as tabs,
    filtered by status and paged, and the suggestions of that kind (what fits their
    wishes, offers and skills; a match once someone asks). Without a type, an overview
    of what's open."""
    kind = request.GET.get("type", "")
    if kind not in _KINDS:
        return _overview(request)

    user = request.user
    boxes = {
        "received": _matches_of(kind).filter(recipient=user),
        "sent":     _matches_of(kind).filter(from_user=user),
    }
    # The owner answers a request; the requester answers the owner's counter-proposal.
    waiting = {
        "received": boxes["received"].filter(status=Match.STATUS_PENDING).count(),
        "sent":     boxes["sent"].filter(status=Match.STATUS_COUNTER).count(),
    }
    counts = {key: matches.count() for key, matches in boxes.items()}
    suggestions = suggestions_of_kind(_suggestions_of(user), kind)
    counts["suggestions"] = suggestions.count()
    waiting["suggestions"] = suggestions.filter(seen_at=None).count()
    box = request.GET.get("box")
    if box not in counts:
        # Open on the tab that needs you, otherwise on the one that has anything
        box = next((key for key in counts if waiting[key]), None) \
            or next((key for key in counts if counts[key]), "received")
    tabs = [
        Choice(label, query_url(request, box=key, status=None), key == box, counts[key], waiting[key])
        for key, label in (("received", _("Received")), ("sent", _("Sent")), ("suggestions", _("Suggestions")))
    ]

    if box == "suggestions":
        page = paginate(request, suggestions)
        shown = _shown(page.object_list)
        return render(request, "matches/matches_list.html", {
            "request_type": kind,
            "kind":         _KINDS[kind],
            "tabs":         tabs,
            "page":         page,
            "suggestions":  shown,
            "new_ids":      _mark_seen(user, shown),
        })

    matches = boxes[box]
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

    return render(request, "matches/matches_list.html", {
        "request_type": kind,
        "kind":         _KINDS[kind],
        "show_from":    box == "received",
        "tabs":         tabs,
        "filters":      filters if counts[box] else [],
        "page":         paginate(request, matches),
    })


def _overview(request):
    """What's open across all kinds of match, a few rows each."""
    user = request.user
    sections = []
    for kind, info in _KINDS.items():
        open_matches = _matches_of(kind).filter(Q(recipient=user) | Q(from_user=user), status__in=_OPEN)
        sections.append({
            **info,
            "url":             f"{reverse('matches:list')}?type={kind}",
            "matches":         list(open_matches[:_OVERVIEW_ROWS]),
            "open_count":      open_matches.count(),
            "suggestions_url": f"{reverse('matches:list')}?type={kind}&box=suggestions",
            "new_suggestions": suggestions_of_kind(_suggestions_of(user), kind).filter(seen_at=None).count(),
        })
    return render(request, "matches/matches_overview.html", {"request_type": "", "sections": sections})


# ── Match detail ────────────────────────────────────────────────────────────────

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

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {"accept": Match.STATUS_ACCEPTED, "decline": Match.STATUS_DECLINED}[action]
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
    })


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
