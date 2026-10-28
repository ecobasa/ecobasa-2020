import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from gifts.models import Listing
from .models import Skill, SkillTaxonomy, get_or_create_skill

# The pages about the skills themselves, in every language. Who offers or wishes for a
# skill are gift listings (gifts.Listing.skill), with the gifts' pages and forms.


def skill_list(request):
    """All canonical skills, ordered by how many people/communities offer them."""
    offers = Listing.objects.current().filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
    skills = (
        Skill.objects
        .annotate(
            user_count=Count("listings", filter=Q(listings__in=offers.filter(community=None)), distinct=True),
            community_count=Count("listings__community", filter=Q(listings__in=offers), distinct=True),
        )
        .order_by("-user_count", "-community_count", "name")
    )
    return render(request, "skills/skill_list.html", {"skills": skills})


def skill_detail(request, slug):
    """Everyone who offers a skill (people and communities) and who looks for it."""
    skill    = get_object_or_404(Skill, slug=slug)
    listings = skill.listings.current().select_related("owner", "community", "project")
    offers   = listings.filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
    user_skills = offers.filter(community=None, available=True).order_by("owner__name")
    comm_skills = offers.exclude(community=None).order_by("community__name")
    wishes   = listings.filter(type=Listing.TYPE_WISH).order_by("-updated_at")
    user_has_skill = request.user.is_authenticated and listings.filter(owner=request.user, community=None).exists()
    return render(request, "skills/skill_detail.html", {
        "skill":          skill,
        "user_skills":    user_skills,
        "comm_skills":    comm_skills,
        "wishes":         wishes,
        "wish_count":     wishes.count(),
        "user_has_skill": user_has_skill,
    })


@login_required
def userskill_add_several(request):
    """Add several skills at once, e.g. the ones from a volunteer request, with a level each.

    GET ?offer=slug,slug&wish=slug lists the skills not yet on the profile; the
    POST adds the ticked ones as skill offers or skills to learn, with level and description.
    """
    data = request.POST if request.method == "POST" else request.GET
    if request.method == "POST":
        slugs = {"offer": data.getlist("offer"), "wish": data.getlist("wish")}
    else:
        slugs = {kind: [s for s in data.get(kind, "").split(",") if s] for kind in ("offer", "wish")}
    mine = Listing.objects.of(request.user).filter(kind=Listing.KIND_SKILL)
    existing = {
        "offer": set(mine.filter(type=Listing.TYPE_OFFER).values_list("skill__slug", flat=True)),
        "wish":  set(mine.filter(type=Listing.TYPE_WISH).values_list("skill__slug", flat=True)),
    }
    # Skills from the taxonomy that nobody has used yet have no Skill row; it is created on save.
    skills = {
        t.slug: Skill(name=t.get_name("en"), slug=t.slug)
        for t in SkillTaxonomy.objects.filter(slug__in=slugs["offer"] + slugs["wish"])
    }
    skills.update(Skill.objects.in_bulk(slugs["offer"] + slugs["wish"], field_name="slug"))
    levels = dict(Listing.LEVEL_CHOICES)
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
            Listing.objects.get_or_create(
                owner=request.user, community=None, type=row["kind"], kind=Listing.KIND_SKILL, skill=row["skill"],
                defaults={"level": level, "description": data.get(row["description_field"], "").strip()},
            )
        if rows:
            messages.success(request, _("Skills added to your profile."))
        return redirect(request.user.get_absolute_url())

    if not rows:
        return redirect(request.user.get_absolute_url())
    return render(request, "skills/userskill_add_several.html", {
        "offer_rows":    [r for r in rows if r["kind"] == "offer"],
        "wish_rows":     [r for r in rows if r["kind"] == "wish"],
        "level_choices": Listing.LEVEL_CHOICES,
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
