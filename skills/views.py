from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from .forms import CommunitySkillForm, SkillRequestForm, UserSkillForm
from .models import CommunitySkill, Skill, UserSkill
from communities.models import Community
from users.models import User


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


def userskill_detail(request, skill_slug, username):
    """One person's skill detail page — description, level, request form."""
    skill      = get_object_or_404(Skill, slug=skill_slug)
    user       = get_object_or_404(User, username=username)
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
                messages.success(request, _("Your request has been sent."))
                return redirect(user_skill.get_absolute_url())
        else:
            form = SkillRequestForm()

    return render(request, "skills/userskill_detail.html", {
        "user_skill": user_skill,
        "skill":      skill,
        "profile":    user,
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
                sr.from_user      = request.user
                sr.community_skill = comm_skill
                sr.save()
                messages.success(request, _("Your request has been sent."))
                return redirect(comm_skill.get_absolute_url())
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
def userskill_edit(request, skill_slug, username):
    if request.user.username != username:
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
def userskill_delete(request, skill_slug, username):
    if request.user.username != username:
        return redirect("users:login")
    skill      = get_object_or_404(Skill, slug=skill_slug)
    user_skill = get_object_or_404(UserSkill, skill=skill, user=request.user)
    if request.method == "POST":
        user_skill.delete()
        messages.success(request, _("Skill removed."))
        return redirect("users:detail", username=username)
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
