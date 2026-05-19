from datetime import datetime as _dt

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from notifications.models import Notification
from .emails import (
    make_action_token, read_action_token,
    send_volunteer_response_email,
    send_ad_response_email,
    send_skill_response_email,
)
from .models import VolunteerRequest, VolunteerRequestMessage


# ── Matches list (all types) ──────────────────────────────────────────────────

@login_required
def matches_list(request):
    from gifting.models import AdRequest
    from skills.models import SkillInterest

    t = request.GET.get("type", "")
    ctx = {"request_type": t}

    if t in ("", "volunteer"):
        ctx["volunteer_mine"]   = VolunteerRequest.objects.filter(from_user=request.user).select_related("community", "community__owner")
        ctx["volunteer_theirs"] = VolunteerRequest.objects.filter(community__owner=request.user).select_related("from_user", "community")

    if t in ("", "freemarket"):
        ctx["fm_mine"]   = AdRequest.objects.filter(from_user=request.user).select_related("ad", "ad__owner")
        ctx["fm_theirs"] = AdRequest.objects.filter(ad__owner=request.user).select_related("from_user", "ad")

    if t in ("", "skills"):
        ctx["skill_mine"]   = SkillInterest.objects.filter(from_user=request.user).select_related(
            "user_skill__skill", "user_skill__user",
            "community_skill__skill", "community_skill__community",
            "wish__skill", "wish__user",
        )
        ctx["skill_theirs"] = SkillInterest.objects.filter(
            Q(user_skill__user=request.user) |
            Q(community_skill__community__owner=request.user) |
            Q(wish__user=request.user)
        ).select_related(
            "from_user",
            "user_skill__skill", "user_skill__user",
            "community_skill__skill", "community_skill__community",
            "wish__skill", "wish__user",
        )

    return render(request, "matches/matches_list.html", ctx)


# ── Volunteer request detail ──────────────────────────────────────────────────

@login_required
def volunteer_detail(request, pk):
    vr = get_object_or_404(
        VolunteerRequest.objects.select_related("community", "community__owner", "from_user"), pk=pk
    )
    user         = request.user
    is_recipient = vr.community.owner == user
    is_sender    = vr.from_user == user

    if not (is_recipient or is_sender):
        raise Http404

    if request.method == "POST":
        action = request.POST.get("action", "")
        body   = request.POST.get("body", "").strip()

        if action in ("accept", "decline") and is_recipient and vr.status == "pending":
            vr.status       = "accepted" if action == "accept" else "declined"
            vr.responded_at = timezone.now()
            vr.save(update_fields=["status", "responded_at"])
            send_volunteer_response_email(vr, request)
            _notify_volunteer_response(vr)

        if body:
            VolunteerRequestMessage.objects.create(request=vr, sender=user, body=body)

        return redirect(vr.get_absolute_url())

    thread = vr.messages.select_related("sender")
    return render(request, "matches/volunteer_detail.html", {
        "vr":            vr,
        "is_recipient":  is_recipient,
        "is_sender":     is_sender,
        "thread":        thread,
        "accept_token":  make_action_token("volunteer", vr.pk, "accept")  if is_recipient else None,
        "decline_token": make_action_token("volunteer", vr.pk, "decline") if is_recipient else None,
        "request_type":  "volunteer",
    })


# ── Gift offer detail ────────────────────────────────────────────────────────

@login_required
def gift_offer_detail(request, pk):
    from gifting.models import AdRequest, AdRequestMessage
    from gifting.forms import AdRequestMessageForm

    ar    = get_object_or_404(AdRequest.objects.select_related("ad", "ad__owner", "from_user"), pk=pk)
    owner = ar.ad.owner

    if request.user != ar.from_user and request.user != owner:
        raise Http404

    is_owner     = request.user == owner
    is_requester = request.user == ar.from_user

    thread = list(ar.thread.select_related("sender").all())
    latest_status_msg  = None
    latest_counter_msg = None
    for msg in reversed(thread):
        if msg.status_to and latest_status_msg is None:
            latest_status_msg = msg
        if msg.status_to == AdRequest.STATUS_COUNTER and latest_counter_msg is None:
            latest_counter_msg = msg
        if latest_status_msg and latest_counter_msg:
            break

    counter_by_owner  = (
        ar.status == AdRequest.STATUS_COUNTER
        and latest_status_msg is not None
        and latest_status_msg.sender_id == owner.pk
    )
    owner_can_decide     = is_owner and not counter_by_owner
    requester_can_decide = is_requester and counter_by_owner

    if request.method == "POST":
        action = request.POST.get("action", "message")

        if action == "message":
            body = request.POST.get("body", "").strip()
            if body:
                AdRequestMessage.objects.create(request=ar, sender=request.user, body=body)
            return redirect(ar.get_absolute_url())

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {"accept": AdRequest.STATUS_ACCEPTED, "decline": AdRequest.STATUS_DECLINED}[action]
            AdRequestMessage.objects.create(
                request=ar, sender=request.user,
                body=request.POST.get("body", "").strip(), status_to=new_status,
            )
            ar.status       = new_status
            ar.responded_at = timezone.now()
            ar.save()
            _notify_ad_response(ar, actor=request.user, http_request=request)
            flash.success(request, _("Response sent."))
            return redirect(ar.get_absolute_url())

        if action == "counter" and is_owner:
            msg = AdRequestMessage(
                request=ar, sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=AdRequest.STATUS_COUNTER,
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
            ar.status       = AdRequest.STATUS_COUNTER
            ar.responded_at = timezone.now()
            ar.save()
            _notify_ad_response(ar, actor=request.user, http_request=request)
            flash.success(request, _("Counter-proposal sent."))
            return redirect(ar.get_absolute_url())

    return render(request, "matches/gift_offer_detail.html", {
        "ar":                   ar,
        "owner":                owner,
        "is_owner":             is_owner,
        "is_requester":         is_requester,
        "thread":               thread,
        "latest_status_msg":    latest_status_msg,
        "latest_counter_msg":   latest_counter_msg,
        "owner_can_decide":     owner_can_decide,
        "requester_can_decide": requester_can_decide,
        "message_form":         AdRequestMessageForm(),
        "loc_choices":          AdRequest.LOC_CHOICES,
        "request_type":         "freemarket",
    })


# ── Skill interest detail ────────────────────────────────────────────────────

@login_required
def skill_interest_detail(request, pk):
    from skills.models import SkillInterest, SkillInterestMessage
    from skills.forms import SkillInterestMessageForm

    sr = get_object_or_404(
        SkillInterest.objects.select_related(
            "user_skill__user", "user_skill__skill",
            "community_skill__community__owner", "community_skill__skill",
            "wish__user", "wish__community__owner", "wish__skill",
            "from_user",
        ), pk=pk
    )

    if sr.wish:
        owner = sr.wish.user or (sr.wish.community.owner if sr.wish.community else None)
    elif sr.user_skill:
        owner = sr.user_skill.user
    else:
        owner = sr.community_skill.community.owner

    if request.user != sr.from_user and request.user != owner:
        raise Http404

    is_owner     = request.user == owner
    is_requester = request.user == sr.from_user

    thread = list(sr.thread.select_related("sender").all())
    latest_status_msg  = None
    latest_counter_msg = None
    for msg in reversed(thread):
        if msg.status_to and latest_status_msg is None:
            latest_status_msg = msg
        if msg.status_to == SkillInterest.STATUS_COUNTER and latest_counter_msg is None:
            latest_counter_msg = msg
        if latest_status_msg and latest_counter_msg:
            break

    counter_by_owner  = (
        sr.status == SkillInterest.STATUS_COUNTER
        and latest_status_msg is not None
        and latest_status_msg.sender_id == owner.pk
    )
    owner_can_decide     = is_owner and not counter_by_owner
    requester_can_decide = is_requester and counter_by_owner

    if request.method == "POST":
        action = request.POST.get("action", "message")

        if action == "message":
            body = request.POST.get("body", "").strip()
            if body:
                SkillInterestMessage.objects.create(interest=sr, sender=request.user, body=body)
            return redirect(sr.get_absolute_url())

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {
                "accept":  SkillInterest.STATUS_ACCEPTED,
                "decline": SkillInterest.STATUS_DECLINED,
            }[action]
            SkillInterestMessage.objects.create(
                interest=sr, sender=request.user,
                body=request.POST.get("body", "").strip(), status_to=new_status,
            )
            sr.status       = new_status
            sr.responded_at = timezone.now()
            sr.save()
            _notify_skill_response(sr, actor=request.user, http_request=request)
            flash.success(request, _("Response sent."))
            return redirect(sr.get_absolute_url())

        if action == "counter" and is_owner:
            msg = SkillInterestMessage(
                interest=sr, sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=SkillInterest.STATUS_COUNTER,
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
            sr.status       = SkillInterest.STATUS_COUNTER
            sr.responded_at = timezone.now()
            sr.save()
            _notify_skill_response(sr, actor=request.user, http_request=request)
            flash.success(request, _("Counter-proposal sent."))
            return redirect(sr.get_absolute_url())

    return render(request, "matches/skill_interest_detail.html", {
        "sr":                   sr,
        "owner":                owner,
        "is_owner":             is_owner,
        "is_requester":         is_requester,
        "thread":               thread,
        "latest_status_msg":    latest_status_msg,
        "latest_counter_msg":   latest_counter_msg,
        "owner_can_decide":     owner_can_decide,
        "requester_can_decide": requester_can_decide,
        "message_form":         SkillInterestMessageForm(),
        "loc_choices":          SkillInterest.LOC_CHOICES,
        "request_type":         "skills",
    })


# ── Email token action (no login required) ────────────────────────────────────

def email_action(request, token):
    """Accept or decline any request type via signed link in email — no login required."""
    try:
        payload = read_action_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid or expired link.")

    request_type = payload.get("type", "volunteer")
    pk           = payload["id"]
    action       = payload["action"]

    if request_type == "volunteer":
        return _email_action_volunteer(request, pk, action)
    elif request_type == "ad_request":
        return _email_action_ad(request, pk, action)
    elif request_type == "skill_interest":
        return _email_action_skill(request, pk, action)
    else:
        return HttpResponseBadRequest("Unknown request type.")


def _email_action_volunteer(request, pk, action):
    vr = get_object_or_404(VolunteerRequest, pk=pk)
    if vr.status != "pending":
        flash.info(request, _("This interest has already been responded to."))
        return redirect(vr.get_absolute_url())

    vr.status       = "accepted" if action == "accept" else "declined"
    vr.responded_at = timezone.now()
    vr.save(update_fields=["status", "responded_at"])
    send_volunteer_response_email(vr, request)
    _notify_volunteer_response(vr)

    return render(request, "matches/email_action_done.html", {
        "action": action, "title": vr.community.name, "detail_url": vr.get_absolute_url(),
    })


def _email_action_ad(request, pk, action):
    from gifting.models import AdRequest, AdRequestMessage
    ar = get_object_or_404(AdRequest.objects.select_related("ad", "ad__owner", "from_user"), pk=pk)
    if ar.status != AdRequest.STATUS_PENDING:
        flash.info(request, _("This interest has already been responded to."))
        return redirect(ar.get_absolute_url())

    actor           = ar.ad.owner
    ar.status       = AdRequest.STATUS_ACCEPTED if action == "accept" else AdRequest.STATUS_DECLINED
    ar.responded_at = timezone.now()
    ar.save(update_fields=["status", "responded_at"])
    AdRequestMessage.objects.create(request=ar, sender=actor, body="", status_to=ar.status)
    send_ad_response_email(ar, actor, request)
    _notify_ad_response_from_token(ar, actor)

    return render(request, "matches/email_action_done.html", {
        "action": action, "title": ar.ad.title, "detail_url": ar.get_absolute_url(),
    })


def _email_action_skill(request, pk, action):
    from skills.models import SkillInterest, SkillInterestMessage
    sr = get_object_or_404(
        SkillInterest.objects.select_related(
            "user_skill", "user_skill__user", "user_skill__skill",
            "community_skill", "community_skill__community",
            "community_skill__community__owner", "community_skill__skill",
            "from_user",
        ), pk=pk,
    )
    if sr.status != SkillInterest.STATUS_PENDING:
        flash.info(request, _("This interest has already been responded to."))
        return redirect(sr.get_absolute_url())

    if sr.user_skill:
        actor      = sr.user_skill.user
        skill_name = sr.user_skill.skill.name
    else:
        actor      = sr.community_skill.community.owner
        skill_name = sr.community_skill.skill.name

    sr.status       = SkillInterest.STATUS_ACCEPTED if action == "accept" else SkillInterest.STATUS_DECLINED
    sr.responded_at = timezone.now()
    sr.save(update_fields=["status", "responded_at"])
    SkillInterestMessage.objects.create(interest=sr, sender=actor, body="", status_to=sr.status)
    send_skill_response_email(sr, actor, request)
    _notify_skill_response_from_token(sr, actor, skill_name)

    return render(request, "matches/email_action_done.html", {
        "action": action, "title": skill_name, "detail_url": sr.get_absolute_url(),
    })


# ── Notification helpers ──────────────────────────────────────────────────────

def _notify_volunteer_response(vr):
    from django.utils.translation import gettext as _g
    Notification.objects.create(
        recipient=vr.from_user,
        actor=vr.community.owner,
        verb=_g("Your volunteer stay request at %(c)s was %(status)s") % {
            "c": vr.community.name, "status": vr.get_status_display().lower(),
        },
        link=vr.get_absolute_url(),
        tag="accepted" if vr.status == "accepted" else "declined",
    )


def _notify_ad_response(ad_request, actor, http_request=None):
    from gifting.models import AdRequest
    from django.utils.translation import gettext as _g
    ad    = ad_request.ad
    owner = ad.owner
    recipient = ad_request.from_user if actor == owner else owner
    if recipient is None:
        return
    tag_map = {
        AdRequest.STATUS_ACCEPTED: "gift_accepted",
        AdRequest.STATUS_DECLINED: "gift_declined",
        AdRequest.STATUS_COUNTER:  "gift_counter",
    }
    tag        = tag_map.get(ad_request.status, "")
    actor_name = actor.name or actor.email
    verb = _g("%(actor)s %(status)s your interest in: %(title)s") % {
        "actor": actor_name, "status": ad_request.get_status_display().lower(), "title": ad.title,
    }
    Notification.objects.create(
        recipient=recipient, actor=actor,
        verb=str(verb), link=ad_request.get_absolute_url(), tag=tag,
    )
    if http_request:
        send_ad_response_email(ad_request, actor, http_request)


def _notify_skill_response(skill_interest, actor, http_request=None):
    from skills.models import SkillInterest
    from django.utils.translation import gettext as _g
    if skill_interest.user_skill:
        skill_name = skill_interest.user_skill.skill.name
        owner      = skill_interest.user_skill.user
    elif skill_interest.wish:
        skill_name = skill_interest.wish.skill.name
        owner      = skill_interest.wish.user or (skill_interest.wish.community.owner if skill_interest.wish.community else None)
    else:
        skill_name = skill_interest.community_skill.skill.name
        owner      = skill_interest.community_skill.community.owner
    recipient = skill_interest.from_user if actor == owner else owner
    if recipient is None:
        return
    tag_map = {
        SkillInterest.STATUS_ACCEPTED: "accepted",
        SkillInterest.STATUS_DECLINED: "declined",
        SkillInterest.STATUS_COUNTER:  "counter",
    }
    tag        = tag_map.get(skill_interest.status, "")
    actor_name = actor.name or actor.email
    verb = _g("%(actor)s %(status)s your skill interest in: %(skill)s") % {
        "actor": actor_name, "status": skill_interest.get_status_display().lower(), "skill": skill_name,
    }
    Notification.objects.create(
        recipient=recipient, actor=actor,
        verb=str(verb), link=skill_interest.get_absolute_url(), tag=tag,
    )
    if http_request:
        send_skill_response_email(skill_interest, actor, http_request)


def _notify_ad_response_from_token(ar, actor):
    from django.utils.translation import gettext as _g
    tag_map = {"accepted": "gift_accepted", "declined": "gift_declined"}
    Notification.objects.create(
        recipient=ar.from_user,
        actor=actor,
        verb=_g("%(actor)s %(status)s your interest in: %(title)s") % {
            "actor": actor.name or actor.email,
            "status": ar.get_status_display().lower(),
            "title": ar.ad.title,
        },
        link=ar.get_absolute_url(),
        tag=tag_map.get(ar.status, ""),
    )


def _notify_skill_response_from_token(sr, actor, skill_name):
    from django.utils.translation import gettext as _g
    tag_map = {"accepted": "accepted", "declined": "declined"}
    Notification.objects.create(
        recipient=sr.from_user,
        actor=actor,
        verb=_g("%(actor)s %(status)s your skill interest in: %(skill)s") % {
            "actor": actor.name or actor.email,
            "status": sr.get_status_display().lower(),
            "skill": skill_name,
        },
        link=sr.get_absolute_url(),
        tag=tag_map.get(sr.status, ""),
    )
