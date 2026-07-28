from datetime import datetime as _dt

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .emails import notify_match_response, read_action_token
from .forms import MatchMessageForm
from .models import Match, MatchMessage

# Maps the list view's "type" query param to the app that owns that kind of match.
# Kept as gifting/skills/communities app labels rather than importing their models —
# matches never needs to import a domain app to work with a Match generically.
_TAB_APP_LABELS = {
    "freemarket": "gifting",
    "skills":     "skills",
    "volunteer":  "communities",
}


def _matches_for(user, direction_field, tab):
    app_label = _TAB_APP_LABELS[tab]
    return list(
        Match.objects
        .filter(content_type__app_label=app_label, **{direction_field: user})
        .select_related("content_type", "from_user", "recipient")
        .prefetch_related("target")
    )


# ── Matches list (all types) ──────────────────────────────────────────────────

@login_required
def matches_list(request):
    t = request.GET.get("type", "")
    ctx = {"request_type": t}

    if t in ("", "volunteer"):
        ctx["volunteer_theirs"] = _matches_for(request.user, "recipient", "volunteer")
        ctx["volunteer_mine"]   = _matches_for(request.user, "from_user", "volunteer")

    if t in ("", "freemarket"):
        ctx["fm_theirs"] = _matches_for(request.user, "recipient", "freemarket")
        ctx["fm_mine"]   = _matches_for(request.user, "from_user", "freemarket")

    if t in ("", "skills"):
        ctx["skill_theirs"] = _matches_for(request.user, "recipient", "skills")
        ctx["skill_mine"]   = _matches_for(request.user, "from_user", "skills")

    return render(request, "matches/matches_list.html", ctx)


# ── Match detail ────────────────────────────────────────────────────────────────

@login_required
def match_detail(request, pk):
    match = get_object_or_404(
        Match.objects.select_related("content_type", "from_user", "recipient"), pk=pk
    )
    target = match.target
    if target is None:
        raise Http404

    if request.user != match.from_user and request.user != match.recipient:
        raise Http404

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
            return redirect(match.get_absolute_url())

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {"accept": Match.STATUS_ACCEPTED, "decline": Match.STATUS_DECLINED}[action]
            MatchMessage.objects.create(
                match=match, sender=request.user,
                body=request.POST.get("body", "").strip(), status_to=new_status,
            )
            match.status       = new_status
            match.responded_at = timezone.now()
            match.save()
            notify_match_response(match, actor=request.user, http_request=request)
            flash.success(request, _("Response sent."))
            return redirect(match.get_absolute_url())

        if action == "counter" and is_owner:
            msg = MatchMessage(
                match=match, sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=Match.STATUS_COUNTER,
            )
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
            notify_match_response(match, actor=request.user, http_request=request)
            flash.success(request, _("Counter-proposal sent."))
            return redirect(match.get_absolute_url())

    return render(request, "matches/match_detail.html", {
        "match":                match,
        "target":               target,
        "is_owner":             is_owner,
        "is_requester":         is_requester,
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
