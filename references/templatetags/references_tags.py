from django import template
from django.contrib.contenttypes.models import ContentType

from ..forms import ReferenceForm
from ..models import Reference, references_about, subject_owner

register = template.Library()


@register.inclusion_tag("references/_references.html", takes_context=True)
def references_for(context, subject):
    """Render the references section for a user, community, listing or skill."""
    request = context["request"]
    content_type = ContentType.objects.get_for_model(subject)
    references = list(references_about(subject).select_related("author").prefetch_related("subject"))
    for reference in references:
        # On a profile, references about the person's listings and skills are listed too
        reference.about_other = (reference.content_type_id, reference.object_id) != (content_type.pk, str(subject.pk))
    user = request.user
    own = next(
        (r for r in references if r.author_id == user.pk and not r.about_other), None
    ) if user.is_authenticated else None
    can_write = user.is_authenticated and subject_owner(subject) != user
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
        "own_reference": own,
        "form": ReferenceForm(instance=own) if can_write else None,
    }
