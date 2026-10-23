from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import ReferenceForm
from .models import Reference, ReferenceSkill, is_referenceable, subject_owner


def _redirect_to(subject):
    return redirect(subject.get_absolute_url() + "#references")


@login_required
@require_POST
def save(request, content_type_id, object_id):
    """Create the user's reference about a subject, or update it if they already wrote one."""
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    if not is_referenceable(content_type):
        raise Http404
    try:
        subject = content_type.get_object_for_this_type(pk=object_id)
    except content_type.model_class().DoesNotExist:
        raise Http404
    owner = subject_owner(subject)
    if owner == request.user:
        raise PermissionDenied

    existing = Reference.objects.filter(
        author=request.user, content_type=content_type, object_id=str(subject.pk)
    ).first()
    form = ReferenceForm(request.POST, instance=existing, subject=subject)
    if form.is_valid():
        reference = form.save(commit=False)
        reference.author = request.user
        reference.recipient = owner
        reference.subject = subject
        reference.save()
        form.save_tags(reference, holder=subject)
        messages.success(request, _("Thank you for sharing your experience."))
    else:
        messages.error(request, _("Please choose an impression and describe your experience."))
    return _redirect_to(subject)


@login_required
@require_POST
def delete(request, pk):
    reference = get_object_or_404(Reference, pk=pk, author=request.user)
    subject = reference.subject
    reference.delete()
    messages.success(request, _("Your reference was removed."))
    return _redirect_to(subject)


@login_required
@require_POST
def skill_tag(request, pk, action):
    """The person (or community owner) a reference is about confirms or declines a skill
    tagged on it. Confirming adds the skill to their profile."""
    tag = get_object_or_404(ReferenceSkill.objects.select_related("reference", "skill"), pk=pk)
    subject = tag.reference.subject
    if action not in ("confirm", "decline") or subject is None or subject_owner(subject) != request.user:
        raise Http404
    if action == "confirm":
        tag.confirm()
        messages.success(request, _("%(skill)s was added to your skills.") % {"skill": tag.skill.get_name()})
    else:
        tag.decline()
    return _redirect_to(subject)
