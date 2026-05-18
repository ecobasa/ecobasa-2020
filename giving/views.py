from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from notifications.models import Notification
from .emails import make_action_token, read_action_token, send_volunteer_response_email
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
    vr = get_object_or_404(VolunteerRequest.objects.select_related("community", "community__owner", "from_user"), pk=pk)
    user = request.user
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
            _notify_response(vr)

        if body:
            VolunteerRequestMessage.objects.create(request=vr, sender=user, body=body)

        return redirect(vr.get_absolute_url())

    thread = vr.messages.select_related("sender")
    return render(request, "giving/volunteer_detail.html", {
        "vr":           vr,
        "is_recipient": is_recipient,
        "is_sender":    is_sender,
        "thread":       thread,
        "accept_token": make_action_token(vr.pk, "accept")  if is_recipient else None,
        "decline_token": make_action_token(vr.pk, "decline") if is_recipient else None,
    })


def email_action(request, token):
    """Approve or decline via signed link in email — no login required."""
    try:
        payload = read_action_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid or expired link.")

    vr     = get_object_or_404(VolunteerRequest, pk=payload["id"])
    action = payload["action"]

    if vr.status != "pending":
        flash.info(request, _("This request has already been responded to."))
        return redirect(vr.get_absolute_url())

    vr.status       = "accepted" if action == "accept" else "declined"
    vr.responded_at = timezone.now()
    vr.save(update_fields=["status", "responded_at"])
    send_volunteer_response_email(vr, request)
    _notify_response(vr)

    return render(request, "giving/email_action_done.html", {"vr": vr, "action": action})


def _notify_response(vr):
    from django.utils.translation import gettext as _g
    tag  = "accepted" if vr.status == "accepted" else "declined"
    verb = _g("Your volunteer stay request at %(c)s was %(status)s") % {
        "c":      vr.community.name,
        "status": vr.get_status_display().lower(),
    }
    Notification.objects.create(
        recipient=vr.from_user,
        actor=vr.community.owner,
        verb=verb,
        link=vr.get_absolute_url(),
        tag=tag,
    )
