from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from django.utils.text import slugify

from .forms import CommunitySkillForm, SkillRequestForm, SkillRequestResponseForm, SkillRequestMessageForm, UserSkillForm
from .models import CommunitySkill, Skill, SkillRequest, SkillRequestMessage, UserSkill
from communities.models import Community
from users.models import User


def _notify_skill_request(skill_request):
    """Create an in-app notification and send an email for a new SkillRequest."""
    from notifications.models import Notification

    if skill_request.user_skill:
        recipient = skill_request.user_skill.user
        skill_name = skill_request.user_skill.skill.name
    else:
        community = skill_request.community_skill.community
        recipient = community.owner
        skill_name = skill_request.community_skill.skill.name

    if recipient is None:
        return

    link = skill_request.get_absolute_url()
    actor_name = skill_request.from_user.name or skill_request.from_user.email
    verb = _("%(actor)s requested your skill: %(skill)s") % {
        "actor": actor_name, "skill": skill_name
    }

    Notification.objects.create(
        recipient=recipient,
        actor=skill_request.from_user,
        verb=str(verb),
        link=link,
        tag="requested",
    )

    location_line = skill_request.resolved_location()
    date_line = str(skill_request.proposed_date) if skill_request.proposed_date else ""

    body = (
        f"{actor_name} has sent a skill request for '{skill_name}'.\n\n"
        f"Message:\n{skill_request.message}\n"
    )
    if location_line:
        body += f"\nLocation: {location_line}"
    if date_line:
        body += f"\nProposed date: {date_line}"
    body += f"\n\nView it here: https://ecobasa.org{link}"

    try:
        send_mail(
            subject=f"[ecobasa] Skill request: {skill_name}",
            message=body,
            from_email="noreply@ecobasa.org",
            recipient_list=[recipient.email],
            fail_silently=True,
        )
    except Exception:
        pass


def _get_user_by_slug(user_slug):
    """Mirrors User.DetailView lookup: username → slugified name → pk."""
    try:
        return User.objects.get(username=user_slug)
    except User.DoesNotExist:
        pass
    try:
        return User.objects.get(name__iexact=user_slug.replace("-", " "))
    except User.DoesNotExist:
        pass
    try:
        return User.objects.get(pk=user_slug)
    except (User.DoesNotExist, ValueError, TypeError):
        pass
    return None


def skill_list(request):
    """All canonical skills, ordered by how many people/communities have them."""
    from django.db.models import Count
    skills = (
        Skill.objects
        .annotate(
            user_count=Count("user_skills", distinct=True),
            community_count=Count("community_skills", distinct=True),
        )
        .order_by("-user_count", "-community_count", "name")
    )
    return render(request, "skills/skill_list.html", {"skills": skills})


def skill_detail(request, slug):
    """All people and communities that share a given skill."""
    skill        = get_object_or_404(Skill, slug=slug)
    user_skills  = skill.user_skills.filter(available=True).select_related("user").order_by("user__name")
    comm_skills  = skill.community_skills.select_related("community").order_by("community__name")
    return render(request, "skills/skill_detail.html", {
        "skill":       skill,
        "user_skills": user_skills,
        "comm_skills": comm_skills,
    })


def userskill_detail(request, skill_slug, user_slug):
    """One person's skill detail page — description, level, request form."""
    skill      = get_object_or_404(Skill, slug=skill_slug)
    user       = _get_user_by_slug(user_slug)
    if user is None:
        raise Http404("User not found")
    user_skill = get_object_or_404(UserSkill, skill=skill, user=user)

    form = None
    if request.user.is_authenticated and request.user != user:
        if request.method == "POST":
            form = SkillRequestForm(request.POST)
            if form.is_valid():
                sr = form.save(commit=False)
                sr.from_user   = request.user
                sr.user_skill  = user_skill
                sr.save()
                _notify_skill_request(sr)
                messages.success(request, _("Your request has been sent."))
                return redirect(sr.get_absolute_url())
        else:
            form = SkillRequestForm()

    from .models import _user_slug as _slug
    return render(request, "skills/userskill_detail.html", {
        "user_skill": user_skill,
        "skill":      skill,
        "profile":    user,
        "user_slug":  _slug(user),
        "form":       form,
    })


def communityskill_detail(request, skill_slug, community_slug):
    """A community's skill detail page — description and request form."""
    skill      = get_object_or_404(Skill, slug=skill_slug)
    community  = get_object_or_404(Community, slug=community_slug)
    comm_skill = get_object_or_404(CommunitySkill, skill=skill, community=community)

    form = None
    if request.user.is_authenticated:
        if request.method == "POST":
            form = SkillRequestForm(request.POST)
            if form.is_valid():
                sr = form.save(commit=False)
                sr.from_user       = request.user
                sr.community_skill = comm_skill
                sr.save()
                _notify_skill_request(sr)
                messages.success(request, _("Your request has been sent."))
                return redirect(sr.get_absolute_url())
        else:
            form = SkillRequestForm()

    return render(request, "skills/communityskill_detail.html", {
        "comm_skill": comm_skill,
        "skill":      skill,
        "community":  community,
        "form":       form,
    })


# ── User skill management ────────────────────────────────────────────

@login_required
def userskill_add(request):
    if request.method == "POST":
        form = UserSkillForm(request.POST)
        if form.is_valid():
            us = form.save(commit=False)
            us.user = request.user
            try:
                us.save()
                messages.success(request, _("Skill added."))
                return redirect(us.get_absolute_url())
            except Exception:
                messages.error(request, _("You already have this skill listed."))
    else:
        form = UserSkillForm()
    return render(request, "skills/userskill_form.html", {"form": form, "action": "add"})


@login_required
def userskill_edit(request, skill_slug, user_slug):
    user = _get_user_by_slug(user_slug)
    if user is None or user != request.user:
        return redirect("users:login")
    skill      = get_object_or_404(Skill, slug=skill_slug)
    user_skill = get_object_or_404(UserSkill, skill=skill, user=request.user)
    form = UserSkillForm(request.POST or None, instance=user_skill)
    if form.is_valid():
        form.save()
        messages.success(request, _("Skill updated."))
        return redirect(user_skill.get_absolute_url())
    return render(request, "skills/userskill_form.html", {"form": form, "action": "edit", "user_skill": user_skill})


@login_required
def userskill_delete(request, skill_slug, user_slug):
    user = _get_user_by_slug(user_slug)
    if user is None or user != request.user:
        return redirect("users:login")
    skill      = get_object_or_404(Skill, slug=skill_slug)
    user_skill = get_object_or_404(UserSkill, skill=skill, user=request.user)
    if request.method == "POST":
        user_skill.delete()
        messages.success(request, _("Skill removed."))
        return redirect(request.user.get_absolute_url())
    return render(request, "skills/userskill_confirm_delete.html", {"user_skill": user_skill})


# ── Community skill management ───────────────────────────────────────

@login_required
def communityskill_add(request, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    if community.owner != request.user:
        return redirect("users:login")
    if request.method == "POST":
        form = CommunitySkillForm(request.POST)
        if form.is_valid():
            cs = form.save(commit=False)
            cs.community = community
            try:
                cs.save()
                messages.success(request, _("Skill added."))
                return redirect(cs.get_absolute_url())
            except Exception:
                messages.error(request, _("This community already has this skill listed."))
    else:
        form = CommunitySkillForm()
    return render(request, "skills/communityskill_form.html", {
        "form": form, "community": community, "action": "add"
    })


@login_required
def communityskill_edit(request, skill_slug, community_slug):
    community  = get_object_or_404(Community, slug=community_slug)
    if community.owner != request.user:
        return redirect("users:login")
    skill      = get_object_or_404(Skill, slug=skill_slug)
    comm_skill = get_object_or_404(CommunitySkill, skill=skill, community=community)
    form = CommunitySkillForm(request.POST or None, instance=comm_skill)
    if form.is_valid():
        form.save()
        messages.success(request, _("Skill updated."))
        return redirect(comm_skill.get_absolute_url())
    return render(request, "skills/communityskill_form.html", {
        "form": form, "community": community, "action": "edit", "comm_skill": comm_skill
    })


@login_required
def communityskill_delete(request, skill_slug, community_slug):
    community  = get_object_or_404(Community, slug=community_slug)
    if community.owner != request.user:
        return redirect("users:login")
    skill      = get_object_or_404(Skill, slug=skill_slug)
    comm_skill = get_object_or_404(CommunitySkill, skill=skill, community=community)
    if request.method == "POST":
        comm_skill.delete()
        messages.success(request, _("Skill removed."))
        return redirect(community.get_absolute_url())
    return render(request, "skills/communityskill_confirm_delete.html", {
        "comm_skill": comm_skill, "community": community
    })


# ── Skill request detail / response ──────────────────────────────────

def _notify_skill_response(skill_request, actor):
    """Notify the other party when a status decision is made."""
    from notifications.models import Notification

    if skill_request.user_skill:
        skill_name = skill_request.user_skill.skill.name
        owner = skill_request.user_skill.user
    else:
        skill_name = skill_request.community_skill.skill.name
        owner = skill_request.community_skill.community.owner

    recipient = skill_request.from_user if actor == owner else owner
    if recipient is None:
        return

    tag_map = {
        SkillRequest.STATUS_ACCEPTED: "accepted",
        SkillRequest.STATUS_DECLINED: "declined",
        SkillRequest.STATUS_COUNTER:  "counter",
    }
    tag = tag_map.get(skill_request.status, "")

    actor_name = actor.name or actor.email
    status_label = skill_request.get_status_display()
    verb = _("%(actor)s %(status)s your skill request: %(skill)s") % {
        "actor": actor_name, "status": status_label.lower(), "skill": skill_name
    }
    link = skill_request.get_absolute_url()

    Notification.objects.create(
        recipient=recipient,
        actor=actor,
        verb=str(verb),
        link=link,
        tag=tag,
    )

    body = f"{actor_name} has {status_label.lower()} the request for '{skill_name}'.\n"
    body += f"\n\nView it here: https://ecobasa.org{link}"

    try:
        send_mail(
            subject=f"[ecobasa] Skill request {status_label.lower()}: {skill_name}",
            message=body,
            from_email="noreply@ecobasa.org",
            recipient_list=[recipient.email],
            fail_silently=True,
        )
    except Exception:
        pass


def skillrequest_detail(request, pk):
    from datetime import datetime as _dt
    sr = get_object_or_404(SkillRequest, pk=pk)

    if sr.user_skill:
        owner = sr.user_skill.user
    else:
        owner = sr.community_skill.community.owner

    if request.user != sr.from_user and request.user != owner:
        if not request.user.is_authenticated:
            return redirect("users:login")
        raise Http404

    is_owner = request.user == owner
    is_requester = request.user == sr.from_user

    # Compute thread before POST so access control can check latest_status_msg
    thread = list(sr.thread.select_related("sender").all())
    latest_status_msg = None
    latest_counter_msg = None
    for msg in reversed(thread):
        if msg.status_to and latest_status_msg is None:
            latest_status_msg = msg
        if msg.status_to == SkillRequest.STATUS_COUNTER and latest_counter_msg is None:
            latest_counter_msg = msg
        if latest_status_msg and latest_counter_msg:
            break

    # Owner can decide unless they sent the latest counter (waiting for requester)
    counter_by_owner = (
        sr.status == SkillRequest.STATUS_COUNTER
        and latest_status_msg is not None
        and latest_status_msg.sender_id == owner.pk
    )
    owner_can_decide = is_owner and not counter_by_owner
    requester_can_decide = is_requester and counter_by_owner

    if request.method == "POST" and request.user.is_authenticated:
        action = request.POST.get("action", "message")

        if action == "message":
            body = request.POST.get("body", "").strip()
            if body:
                SkillRequestMessage.objects.create(
                    request=sr,
                    sender=request.user,
                    body=body,
                )
            return redirect(sr.get_absolute_url())

        if action in ("accept", "decline") and (owner_can_decide or requester_can_decide):
            new_status = {
                "accept":  SkillRequest.STATUS_ACCEPTED,
                "decline": SkillRequest.STATUS_DECLINED,
            }[action]
            SkillRequestMessage.objects.create(
                request=sr,
                sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=new_status,
            )
            sr.status = new_status
            sr.responded_at = timezone.now()
            sr.save()
            _notify_skill_response(sr, actor=request.user)
            messages.success(request, _("Response sent."))
            return redirect(sr.get_absolute_url())

        if action == "counter" and is_owner:
            msg = SkillRequestMessage(
                request=sr,
                sender=request.user,
                body=request.POST.get("body", "").strip(),
                status_to=SkillRequest.STATUS_COUNTER,
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
            sr.status = SkillRequest.STATUS_COUNTER
            sr.responded_at = timezone.now()
            sr.save()
            _notify_skill_response(sr, actor=request.user)
            messages.success(request, _("Counter-proposal sent."))
            return redirect(sr.get_absolute_url())

    return render(request, "skills/skillrequest_detail.html", {
        "sr":                   sr,
        "owner":                owner,
        "is_owner":             is_owner,
        "is_requester":         is_requester,
        "thread":               thread,
        "latest_status_msg":    latest_status_msg,
        "latest_counter_msg":   latest_counter_msg,
        "owner_can_decide":     owner_can_decide,
        "requester_can_decide": requester_can_decide,
        "message_form":         SkillRequestMessageForm(),
        "loc_choices":          SkillRequest.LOC_CHOICES,
    })


# ── Autocomplete API ─────────────────────────────────────────────────

@require_GET
def skill_autocomplete(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse([], safe=False)
    names = list(
        Skill.objects.filter(name__icontains=q).values_list("name", flat=True)[:10]
    )
    return JsonResponse(names, safe=False)
