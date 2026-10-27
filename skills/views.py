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

from .forms import CommunitySkillForm, CommunitySkillOrWishForm, SkillWishEditForm, UserSkillForm, UserSkillOrWishForm
from .models import CommunitySkill, Skill, SkillWish, SkillTaxonomy, UserSkill, get_or_create_skill
from communities.models import Community
from users.models import User
from matches.forms import MatchForm
from matches.emails import notify_match_created


def _get_user_by_slug(user_slug):
    """Same lookup as the user profile page, see UserManager.get_by_slug."""
    return User.objects.get_by_slug(user_slug)


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
    wish_count   = skill.wishes.count()
    user_has_skill = (
        request.user.is_authenticated and (
            skill.user_skills.filter(user=request.user).exists() or
            skill.wishes.filter(user=request.user).exists()
        )
    )
    return render(request, "skills/skill_detail.html", {
        "skill":          skill,
        "user_skills":    user_skills,
        "comm_skills":    comm_skills,
        "wish_count":     wish_count,
        "user_has_skill": user_has_skill,
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
            form = MatchForm(request.POST)
            if form.is_valid():
                match = form.save(commit=False)
                match.from_user = request.user
                match.recipient = user_skill.get_match_owner()
                match.target    = user_skill
                match.save()
                notify_match_created(match, http_request=request)
                messages.success(request, _("Your interest has been sent."))
                return redirect(match.get_absolute_url())
        else:
            form = MatchForm()

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
            form = MatchForm(request.POST)
            if form.is_valid():
                match = form.save(commit=False)
                match.from_user = request.user
                match.recipient = comm_skill.get_match_owner()
                match.target    = comm_skill
                match.save()
                notify_match_created(match, http_request=request)
                messages.success(request, _("Your interest has been sent."))
                return redirect(match.get_absolute_url())
        else:
            form = MatchForm()

    return render(request, "skills/communityskill_detail.html", {
        "comm_skill": comm_skill,
        "skill":      skill,
        "community":  community,
        "form":       form,
    })


# ── User skill management ────────────────────────────────────────────

@login_required
def mine(request):
    """Your skills in the dashboard, with their photo, description, references and
    requests; and the skills you would like to learn."""
    from collections import Counter
    from django.contrib.contenttypes.models import ContentType
    from django.db.models import Count
    from dashboard_lists import Choice, query_url
    from references.models import Reference

    box = "wish" if request.GET.get("box") == "wish" else "offer"
    from matches.models import Match

    skills = list(request.user.user_skills.select_related("skill").annotate(
        extra_count=Count("extra_matches", distinct=True),
    ).order_by("skill__name"))
    # Generic relations are keyed by text, so these are counted per id
    about = {"content_type": ContentType.objects.get_for_model(UserSkill), "object_id__in": [str(us.pk) for us in skills]}
    references = Counter(Reference.objects.filter(**about).values_list("object_id", flat=True))
    requests = Counter(Match.objects.filter(**about).values_list("object_id", flat=True))
    for us in skills:
        us.reference_count = references[str(us.pk)]
        us.request_count = requests[str(us.pk)] + us.extra_count
    wishes = list(request.user.skill_wishes.select_related("skill").order_by("skill__name"))
    tabs = [
        Choice(label, query_url(request, box=key), key == box, count)
        for key, label, count in (("offer", _("Your skills"), len(skills)), ("wish", _("Skills you would like to learn"), len(wishes)))
    ]
    return render(request, "skills/mine.html", {"tabs": tabs, "box": box, "skills": skills, "wishes": wishes})


@login_required
def userskill_add(request):
    initial_mode = request.GET.get("mode", UserSkillOrWishForm.MODE_OFFER)
    if initial_mode not in (UserSkillOrWishForm.MODE_OFFER, UserSkillOrWishForm.MODE_WISH):
        initial_mode = UserSkillOrWishForm.MODE_OFFER

    if request.method == "POST":
        form = UserSkillOrWishForm(request.POST, request.FILES)
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
def userskill_add_several(request):
    """Add several skills at once, e.g. the ones from a volunteer request, with a level each.

    GET ?offer=slug,slug&wish=slug lists the skills not yet on the profile; the
    POST adds the ticked ones as skill offers or learning goals, with level and description.
    """
    data = request.POST if request.method == "POST" else request.GET
    if request.method == "POST":
        slugs = {"offer": data.getlist("offer"), "wish": data.getlist("wish")}
    else:
        slugs = {kind: [s for s in data.get(kind, "").split(",") if s] for kind in ("offer", "wish")}
    existing = {
        "offer": set(request.user.user_skills.values_list("skill__slug", flat=True)),
        "wish":  set(request.user.skill_wishes.values_list("skill__slug", flat=True)),
    }
    # Skills from the taxonomy that nobody has used yet have no Skill row; it is created on save.
    skills = {
        t.slug: Skill(name=t.get_name("en"), slug=t.slug)
        for t in SkillTaxonomy.objects.filter(slug__in=slugs["offer"] + slugs["wish"])
    }
    skills.update(Skill.objects.in_bulk(slugs["offer"] + slugs["wish"], field_name="slug"))
    levels = dict(UserSkill.LEVEL_CHOICES)
    rows = [
        {"kind": kind, "skill": skills[slug],
         "level_field": f"level_{kind}_{slug}", "description_field": f"description_{kind}_{slug}"}
        for kind in ("offer", "wish")
        for slug in dict.fromkeys(slugs[kind])
        if slug in skills and slug not in existing[kind]
    ]

    if request.method == "POST":
        for row in rows:
            level = data.get(row["level_field"], "")
            level = level if level in levels else ""
            if row["skill"].pk is None:
                row["skill"], _created = get_or_create_skill(slug=row["skill"].slug)
            defaults = {"level": level, "description": data.get(row["description_field"], "").strip()}
            if row["kind"] == "offer":
                UserSkill.objects.get_or_create(user=request.user, skill=row["skill"], defaults=defaults)
            else:
                SkillWish.objects.get_or_create(user=request.user, skill=row["skill"], defaults=defaults)
        if rows:
            messages.success(request, _("Skills added to your profile."))
        return redirect(request.user.get_absolute_url())

    if not rows:
        return redirect(request.user.get_absolute_url())
    return render(request, "skills/userskill_add_several.html", {
        "offer_rows":    [r for r in rows if r["kind"] == "offer"],
        "wish_rows":     [r for r in rows if r["kind"] == "wish"],
        "level_choices": UserSkill.LEVEL_CHOICES,
    })


@login_required
def userskill_edit(request, skill_slug, user_slug):
    user = _get_user_by_slug(user_slug)
    if user is None or user != request.user:
        return redirect("users:login")
    skill      = get_object_or_404(Skill, slug=skill_slug)
    user_skill = get_object_or_404(UserSkill, skill=skill, user=request.user)
    form = UserSkillForm(request.POST or None, request.FILES or None, instance=user_skill)
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
                form = MatchForm(request.POST)
                if form.is_valid():
                    match = form.save(commit=False)
                    match.from_user = request.user
                    match.recipient = wish.get_match_owner()
                    match.target    = wish
                    match.save()
                    notify_match_created(match, http_request=request)
                    messages.success(request, _("Your offer has been sent."))
                    return redirect(match.get_absolute_url())
            else:
                form = MatchForm()

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

# Curated "offer" proposals — ordered by community need, NOT by usage.
# Rationale: communities always need construction, maintenance, and everyday
# support skills more than they need the popular skills everyone already lists.
_OFFER_PROPOSAL_SLUGS = [
    # Everyday — universal, low-barrier, always needed in any community
    "kitchen-help", "meal-preparation", "garden-maintenance", "harvesting", "painting-walls", "childcare", "elder-care", "pet-care",
    # Construction & maintenance — every community has broken things
    "carpentry", "plumbing", "electrical-installation", "woodworking", "natural-building",
    # Energy & water systems — high-value for off-grid communities
    "passive-solar-design", "solar-thermal", "solar-panel-installation", "rainwater-harvesting", "water-system-maintenance", "bicycle-repair",
    # Health — first aid and basic care are universally valued
    "medical-practice", "first-aid", "massage-therapy", "herbal-medicine",
    # High-value pro-bono — rare and extremely useful for community governance
    "bookkeeping", "translation", "legal-advice", "social-media", "filmmaking", "fundraising", "permaculture", "permaculture-design",
]

_SKILL_LANGS = [code for code, _ in settings.LANGUAGES]


@require_GET
def skill_proposals(request):
    """Return curated offer proposals ordered by community need (not popularity)."""
    lang = getattr(request, "LANGUAGE_CODE", "en")[:2]
    taxonomy = SkillTaxonomy.objects.filter(slug__in=_OFFER_PROPOSAL_SLUGS)
    taxonomy_map = {t.slug: t for t in taxonomy}
    results = []
    for slug in _OFFER_PROPOSAL_SLUGS:
        t = taxonomy_map.get(slug)
        if t:
            results.append({
                "id":   json.dumps({"slug": t.slug, "names": t.names}),
                "text": t.get_name(lang),
            })
    return JsonResponse({"results": results})


@require_GET
def skill_autocomplete(request):
    q    = request.GET.get("q", "").strip()
    lang = getattr(request, "LANGUAGE_CODE", "en")[:2]
    if len(q) < 2:
        return JsonResponse({"results": []})
    from django.db.models import Q
    lang_filter = Q()
    for code in _SKILL_LANGS:
        lang_filter |= Q(**{f"names__{code}__icontains": q})
    results = SkillTaxonomy.objects.filter(lang_filter)[:10]
    return JsonResponse({"results": [
        {
            "id":   json.dumps({"slug": s.slug, "names": s.names}),
            "text": s.get_name(lang),
        }
        for s in results
    ]})
