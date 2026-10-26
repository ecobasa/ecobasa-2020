from urllib.parse import urlencode

from django import template
from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch
from django.utils.translation import gettext as _

from ..forms import ReferenceForm
from ..models import Reference, ReferenceSkill, references_about, match_reference_subject, subject_owner

register = template.Library()


@register.inclusion_tag("references/_references.html", takes_context=True)
def references_for(context, subject):
    """Render the references section for a user, community, listing or skill."""
    request = context["request"]
    user = request.user
    content_type = ContentType.objects.get_for_model(subject)
    is_owner = user.is_authenticated and subject_owner(subject) == user
    references = list(
        references_about(subject)
        .select_related("author", "content_type")
        .prefetch_related(
            "subject",
            Prefetch("skill_tags", queryset=ReferenceSkill.objects.select_related("skill")),
        )
    )
    for reference in references:
        # On a profile, references about the person's listings and skills are listed too
        reference.about_other = (reference.content_type_id, reference.object_id) != (content_type.pk, str(subject.pk))
        reference.can_confirm = is_owner and not reference.about_other
        # Pending skills are only shown to whoever can confirm them, and to the author
        reference.visible_skill_tags = [
            tag for tag in reference.skill_tags.all()
            if tag.status == ReferenceSkill.STATUS_CONFIRMED
            or (tag.status == ReferenceSkill.STATUS_PENDING and (is_owner or reference.author_id == user.pk))
        ]
    own = next(
        (r for r in references if r.author_id == user.pk and not r.about_other), None
    ) if user.is_authenticated else None
    can_write = user.is_authenticated and not is_owner

    form = None
    prefill_gift = prefill_skill = ""
    if can_write:
        form = ReferenceForm(instance=own, subject=subject)
        if form.can_tag:
            # Coming from an accepted match: the gift's name or the skill is filled in
            prefill_gift = request.GET.get("reference_gift", "").strip()[:200]
            prefill_skill = request.GET.get("reference_skill", "").strip()
            if prefill_skill:
                field = form.fields["skill_names"]
                field.initial = ", ".join(n for n in (field.initial, prefill_skill) if n)

    gift_names = list(own.gift_names) if own else []
    if prefill_gift and prefill_gift not in gift_names:
        gift_names.append(prefill_gift)
    listings = getattr(subject, "listings", None)

    return {
        "request": request,
        "csrf_token": context.get("csrf_token"),
        "subject": subject,
        "content_type": content_type,
        "references": references,
        "counts": {
            impression: sum(1 for r in references if r.impression == impression)
            for impression, _label in Reference.IMPRESSION_CHOICES
        },
        "is_owner": is_owner,
        # A community (or one of its skills): the guide adds a note about writing to a group
        "about_community": content_type.model in ("community", "communityskill"),
        "own_reference": own,
        "form": form,
        "gift_names": gift_names,
        # Skills they already list, suggested first in the skill input
        "held_skills": [
            s.get_match_display_name() for s in getattr(subject, "get_reference_subjects", lambda: [])()
            if hasattr(s, "get_skill_holder")
        ] if form and form.can_tag else [],
        "held_skills_header": _("Skills listed here"),
        "gift_suggestions": [l.title for l in listings.all()] if form and form.can_tag and listings is not None else [],
        # Opened right away when coming from a match or from an "Edit" link
        "open_form": bool(prefill_gift or prefill_skill or request.GET.get("edit_reference")),
    }


@register.simple_tag(takes_context=True)
def reference_url_for_match(context, match):
    """Where to write a reference after an accepted match: the other party's page, with the
    gift's name or the skill filled in. Only the name is carried over."""
    found = match_reference_subject(match, context["request"].user)
    if found is None:
        return ""
    page, gift, skill = found
    params = {}
    if gift:
        params["reference_gift"] = gift
    if skill:
        params["reference_skill"] = skill
    query = f"?{urlencode(params)}" if params else ""
    return f"{page.get_absolute_url()}{query}#references"
