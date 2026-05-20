import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from .forms import CommunitySkillForm, CommunitySkillOrWishForm, SkillInterestForm, SkillWishEditForm, UserSkillForm, UserSkillOrWishForm
from .models import CommunitySkill, Skill, SkillInterest, SkillWish, SkillTaxonomy, UserSkill
from communities.models import Community
from users.models import User


def _notify_skill_interest(skill_interest, http_request=None):
    """Create an in-app notification and send an email for a new SkillInterest."""
    from notifications.models import Notification
    from matches.emails import send_skill_interest_email

    if skill_interest.wish:
        wish = skill_interest.wish
        skill_name = wish.skill.name
        recipient = wish.user or (wish.community.owner if wish.community else None)
        verb_template = _("%(actor)s offered to teach you: %(skill)s")
    elif skill_interest.user_skill:
        recipient = skill_interest.user_skill.user
        skill_name = skill_interest.user_skill.skill.name
        verb_template = _("%(actor)s expressed interest in your skill: %(skill)s")
    else:
        community = skill_interest.community_skill.community
        recipient = community.owner
        skill_name = skill_interest.community_skill.skill.name
        verb_template = _("%(actor)s expressed interest in your skill: %(skill)s")

    if recipient is None:
        return

    link = skill_interest.get_absolute_url()
    actor_name = skill_interest.from_user.name or skill_interest.from_user.email
    verb = verb_template % {"actor": actor_name, "skill": skill_name}

    Notification.objects.create(
        recipient=recipient,
        actor=skill_interest.from_user,
        verb=str(verb),
        link=link,
        tag="requested",
    )

    if http_request:
        send_skill_interest_email(skill_interest, http_request)


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
            form = SkillInterestForm(request.POST)
            if form.is_valid():
                sr = form.save(commit=False)
                sr.from_user   = request.user
                sr.user_skill  = user_skill
                sr.save()
                _notify_skill_interest(sr, http_request=request)
                messages.success(request, _("Your interest has been sent."))
                return redirect(sr.get_absolute_url())
        else:
            form = SkillInterestForm()

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
            form = SkillInterestForm(request.POST)
            if form.is_valid():
                sr = form.save(commit=False)
                sr.from_user       = request.user
                sr.community_skill = comm_skill
                sr.save()
                _notify_skill_interest(sr, http_request=request)
                messages.success(request, _("Your interest has been sent."))
                return redirect(sr.get_absolute_url())
        else:
            form = SkillInterestForm()

    return render(request, "skills/communityskill_detail.html", {
        "comm_skill": comm_skill,
        "skill":      skill,
        "community":  community,
        "form":       form,
    })


# ── User skill management ────────────────────────────────────────────

@login_required
def userskill_add(request):
    initial_mode = request.GET.get("mode", UserSkillOrWishForm.MODE_OFFER)
    if initial_mode not in (UserSkillOrWishForm.MODE_OFFER, UserSkillOrWishForm.MODE_WISH):
        initial_mode = UserSkillOrWishForm.MODE_OFFER

    if request.method == "POST":
        form = UserSkillOrWishForm(request.POST)
        if form.is_valid():
            us, wish = form.save(user=request.user)
            if wish is not None:
                messages.success(request, _("Skill wish added."))
                return redirect(request.user.get_absolute_url())
            else:
                messages.success(request, _("Skill added."))
                return redirect(us.get_absolute_url())
    else:
        form = UserSkillOrWishForm(initial={"mode": initial_mode})
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
    initial_mode = request.GET.get("mode", CommunitySkillOrWishForm.MODE_OFFER)
    if initial_mode not in (CommunitySkillOrWishForm.MODE_OFFER, CommunitySkillOrWishForm.MODE_WISH):
        initial_mode = CommunitySkillOrWishForm.MODE_OFFER
    if request.method == "POST":
        form = CommunitySkillOrWishForm(request.POST)
        if form.is_valid():
            cs, wish = form.save(community=community)
            if wish is not None:
                messages.success(request, _("Skill wish added."))
                return redirect(community.get_absolute_url())
            else:
                messages.success(request, _("Skill added."))
                return redirect(cs.get_absolute_url())
    else:
        form = CommunitySkillOrWishForm(initial={"mode": initial_mode})
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


# ── Skill wish detail ────────────────────────────────────────────────

def skillwish_user_detail(request, user_slug, skill_slug):
    """Detail page for a user's skill wish — lets other users offer to teach."""
    skill = get_object_or_404(Skill, slug=skill_slug)
    user  = _get_user_by_slug(user_slug)
    if user is None:
        raise Http404("User not found")
    wish = get_object_or_404(SkillWish, user=user, skill=skill)

    viewer_user_skill = None
    form = None
    if request.user.is_authenticated and request.user != user:
        viewer_user_skill = UserSkill.objects.filter(user=request.user, skill=skill).first()
        if viewer_user_skill:
            if request.method == "POST":
                form = SkillInterestForm(request.POST)
                if form.is_valid():
                    sr = form.save(commit=False)
                    sr.from_user  = request.user
                    sr.user_skill = viewer_user_skill
                    sr.wish       = wish
                    sr.save()
                    _notify_skill_interest(sr, http_request=request)
                    messages.success(request, _("Your offer has been sent."))
                    return redirect(sr.get_absolute_url())
            else:
                form = SkillInterestForm()

    from .models import _user_slug as _slug
    return render(request, "skills/skillwish_user_detail.html", {
        "wish":              wish,
        "skill":             skill,
        "profile":           user,
        "user_slug":         _slug(user),
        "viewer_user_skill": viewer_user_skill,
        "form":              form,
    })


# ── Skill wish edit ──────────────────────────────────────────────────

@login_required
def skillwish_user_edit(request, pk):
    wish = get_object_or_404(SkillWish, pk=pk, user=request.user)
    form = SkillWishEditForm(
        request.POST or None,
        initial={"wish_level": wish.level, "description": wish.description},
    )
    if form.is_valid():
        form.save(wish)
        messages.success(request, _("Skill wish updated."))
        return redirect(request.user.get_absolute_url())
    return render(request, "skills/skillwish_form.html", {
        "form": form, "wish": wish, "owner": request.user,
    })


@login_required
def skillwish_community_edit(request, pk, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    if community.owner != request.user:
        return redirect("users:login")
    wish = get_object_or_404(SkillWish, pk=pk, community=community)
    level_label = _("Minimum level sought")
    form = SkillWishEditForm(
        request.POST or None,
        initial={"wish_level": wish.level, "description": wish.description},
    )
    form.fields["wish_level"].label = level_label
    form.fields["wish_level"].choices = [("", _("Any level — beginners welcome"))] + UserSkill.LEVEL_CHOICES
    if form.is_valid():
        form.save(wish)
        messages.success(request, _("Skill wish updated."))
        return redirect(community.get_absolute_url())
    return render(request, "skills/skillwish_form.html", {
        "form": form, "wish": wish, "community": community,
    })


# ── Autocomplete API ─────────────────────────────────────────────────

_SKILL_LANGS = [code for code, _ in settings.LANGUAGES]


@require_GET
def skill_autocomplete(request):
    q    = request.GET.get("q", "").strip()
    lang = getattr(request, "LANGUAGE_CODE", "en")[:2]
    if len(q) < 2:
        return JsonResponse({"results": []})
    results = SkillTaxonomy.objects.filter(**{f"names__{lang}__icontains": q})[:10]
    return JsonResponse({"results": [
        {
            "id":   json.dumps({"slug": s.slug, "names": s.names}),
            "text": s.get_name(lang),
        }
        for s in results
    ]})
