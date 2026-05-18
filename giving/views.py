from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core import signing
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


@login_required
def request_list(request):
    sent = (
        VolunteerRequest.objects
        .filter(from_user=request.user)
        .select_related("community", "community__owner")
    )
    received = (
        VolunteerRequest.objects
        .filter(community__owner=request.user)
        .select_related("from_user", "community")
    )
    return render(request, "giving/request_list.html", {
        "sent": sent,
        "received": received,
    })


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
    return render(request, "giving/volunteer_detail.html", {
        "vr":            vr,
        "is_recipient":  is_recipient,
        "is_sender":     is_sender,
        "thread":        thread,
        "accept_token":  make_action_token("volunteer", vr.pk, "accept")  if is_recipient else None,
        "decline_token": make_action_token("volunteer", vr.pk, "decline") if is_recipient else None,
    })


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
    elif request_type == "skill_request":
        return _email_action_skill(request, pk, action)
    else:
        return HttpResponseBadRequest("Unknown request type.")


def _email_action_volunteer(request, pk, action):
    from django.utils.translation import gettext as _g
    vr = get_object_or_404(VolunteerRequest, pk=pk)
    if vr.status != "pending":
        flash.info(request, _("This request has already been responded to."))
        return redirect(vr.get_absolute_url())

    vr.status       = "accepted" if action == "accept" else "declined"
    vr.responded_at = timezone.now()
    vr.save(update_fields=["status", "responded_at"])
    send_volunteer_response_email(vr, request)
    _notify_volunteer_response(vr)

    return render(request, "giving/email_action_done.html", {
        "action": action, "title": vr.community.name, "detail_url": vr.get_absolute_url(),
    })


def _email_action_ad(request, pk, action):
    from gifting.models import AdRequest, AdRequestMessage
    ar = get_object_or_404(AdRequest.objects.select_related("ad", "ad__owner", "from_user"), pk=pk)
    if ar.status != AdRequest.STATUS_PENDING:
        flash.info(request, _("This request has already been responded to."))
        return redirect(ar.get_absolute_url())

    actor           = ar.ad.owner
    ar.status       = AdRequest.STATUS_ACCEPTED if action == "accept" else AdRequest.STATUS_DECLINED
    ar.responded_at = timezone.now()
    ar.save(update_fields=["status", "responded_at"])
    AdRequestMessage.objects.create(request=ar, sender=actor, body="", status_to=ar.status)
    send_ad_response_email(ar, actor, request)
    _notify_ad_response_from_token(ar, actor)

    return render(request, "giving/email_action_done.html", {
        "action": action, "title": ar.ad.title, "detail_url": ar.get_absolute_url(),
    })


def _email_action_skill(request, pk, action):
    from skills.models import SkillRequest, SkillRequestMessage
    sr = get_object_or_404(
        SkillRequest.objects.select_related("user_skill", "user_skill__user", "user_skill__skill",
                                            "community_skill", "community_skill__community",
                                            "community_skill__community__owner",
                                            "community_skill__skill", "from_user"),
        pk=pk,
    )
    if sr.status != SkillRequest.STATUS_PENDING:
        flash.info(request, _("This request has already been responded to."))
        return redirect(sr.get_absolute_url())

    if sr.user_skill:
        actor      = sr.user_skill.user
        skill_name = sr.user_skill.skill.name
    else:
        actor      = sr.community_skill.community.owner
        skill_name = sr.community_skill.skill.name

    sr.status       = SkillRequest.STATUS_ACCEPTED if action == "accept" else SkillRequest.STATUS_DECLINED
    sr.responded_at = timezone.now()
    sr.save(update_fields=["status", "responded_at"])
    SkillRequestMessage.objects.create(request=sr, sender=actor, body="", status_to=sr.status)
    send_skill_response_email(sr, actor, request)
    _notify_skill_response_from_token(sr, actor, skill_name)

    return render(request, "giving/email_action_done.html", {
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


def _notify_ad_response_from_token(ar, actor):
    from django.utils.translation import gettext as _g
    tag_map = {
        "accepted": "gift_accepted",
        "declined": "gift_declined",
    }
    Notification.objects.create(
        recipient=ar.from_user,
        actor=actor,
        verb=_g("%(actor)s %(status)s your request: %(title)s") % {
            "actor": actor.name or actor.email,
            "status": ar.get_status_display().lower(),
            "title": ar.ad.title,
        },
        link=ar.get_absolute_url(),
        tag=tag_map.get(ar.status, ""),
    )


def _notify_skill_response_from_token(sr, actor, skill_name):
    from django.utils.translation import gettext as _g
    tag_map = {
        "accepted": "accepted",
        "declined": "declined",
    }
    Notification.objects.create(
        recipient=sr.from_user,
        actor=actor,
        verb=_g("%(actor)s %(status)s your skill request: %(skill)s") % {
            "actor": actor.name or actor.email,
            "status": sr.get_status_display().lower(),
            "skill": skill_name,
        },
        link=sr.get_absolute_url(),
        tag=tag_map.get(sr.status, ""),
    )
