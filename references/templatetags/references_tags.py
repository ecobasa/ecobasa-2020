from django import template
from django.contrib.contenttypes.models import ContentType

from ..forms import ReferenceForm
from ..models import Reference, subject_owner

register = template.Library()


@register.inclusion_tag("references/_references.html", takes_context=True)
def references_for(context, subject):
    """Render the references section for a user, community, listing or skill."""
    request = context["request"]
    content_type = ContentType.objects.get_for_model(subject)
    references = list(
        Reference.objects.filter(content_type=content_type, object_id=str(subject.pk))
        .select_related("author")
    )
    user = request.user
    own = next((r for r in references if r.author_id == user.pk), None) if user.is_authenticated else None
    can_write = user.is_authenticated and subject_owner(subject) != user
    return {
        "request": request,
        "csrf_token": context.get("csrf_token"),
        "subject": subject,
        "content_type": content_type,
        "references": references,
        "counts": {
            tone: sum(1 for r in references if r.tone == tone)
            for tone, _label in Reference.TONE_CHOICES
        },
        "own_reference": own,
        "form": ReferenceForm(instance=own) if can_write else None,
    }
