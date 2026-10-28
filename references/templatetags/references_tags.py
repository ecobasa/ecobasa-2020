from urllib.parse import urlencode

from django import template
from django.contrib.contenttypes.models import ContentType

from ..forms import ReferenceForm, form_context
from ..models import Reference, ReferenceSkill, references_about, with_card_data, match_gift_names, match_reference_subject, match_skill_names, subject_owner

register = template.Library()


@register.inclusion_tag("references/_references.html", takes_context=True)
def references_for(context, subject):
    """Render the references section for a user, community, listing or skill."""
    request = context["request"]
    user = request.user
    content_type = ContentType.objects.get_for_model(subject)
    is_owner = user.is_authenticated and subject_owner(subject) == user
    references = list(with_card_data(references_about(subject)))
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
    prefill_gifts = []
    if can_write:
        form = ReferenceForm(instance=own, subject=subject)
        if form.can_tag:
            # Coming from an accepted match: the gift's name or the skill is filled in
            prefill_gifts = [name.strip()[:200] for name in request.GET.getlist("reference_gift") if name.strip()][:20]
            prefill_skill = ", ".join(name.strip() for name in request.GET.getlist("reference_skill")[:20] if name.strip())
            if prefill_skill:
                field = form.fields["skill_names"]
                field.initial = ", ".join(n for n in (field.initial, prefill_skill) if n)

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
        "own_reference": own,
        **(form_context(subject, form, own, prefill_gifts) if form else {}),
        # Opened right away when coming from a match or from an "Edit" link
        "open_form": bool(prefill_gifts or request.GET.get("reference_skill") or request.GET.get("edit_reference")),
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
    gifts = [name for name in [gift, *match_gift_names(match, context["request"].user)] if name]
    if gifts:
        params["reference_gift"] = gifts
    skills = [name for name in [skill, *match_skill_names(match, context["request"].user)] if name]
    if skills:
        params["reference_skill"] = skills
    query = f"?{urlencode(params, doseq=True)}" if params else ""
    return f"{page.get_absolute_url()}{query}#references"
