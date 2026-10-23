from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import ReferenceForm
from .models import Reference, ReferenceSkill, is_referenceable, references_about, subject_owner
from .notifications import notify_reference_created


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
        if existing is None:
            notify_reference_created(reference)
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
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return _redirect_to(subject)


def _load(references, user, tab, holder=None):
    """Fetch references for the dashboard and mark how each card is shown. Within a
    group, cards about the group's holder itself (you, or the community) skip the
    "about" line."""
    references = list(
        references.select_related("author", "content_type").prefetch_related(
            "subject", Prefetch("skill_tags", queryset=ReferenceSkill.objects.select_related("skill"))
        ).order_by("-created_at")
    )
    for reference in references:
        about_you = (reference.content_type.model, reference.object_id) == ("user", str(user.pk))
        about_holder = holder is not None and (reference.content_type_id, reference.object_id) == (
            ContentType.objects.get_for_model(holder).pk, str(holder.pk)
        )
        reference.about_other = not about_holder
        reference.about_you = about_you
        reference.visible_skill_tags = [
            t for t in reference.skill_tags.all() if t.status != ReferenceSkill.STATUS_DECLINED
        ]
        reference.can_confirm = tab == "received"
    return references


@login_required
def references_list(request):
    """Dashboard: references received (about you, your listings and skills), given (by
    you), or about a community you are ambassador of (?community=<slug>). A community
    can't write references itself, so its references are a page of their own."""
    user = request.user
    community = None
    if request.GET.get("community"):
        community = get_object_or_404(user.communities.prefetch_related("photos"), slug=request.GET["community"])
        tab = "community"
        references = _load(references_about(community), user, "received", holder=community)
    elif request.GET.get("type") == "given":
        tab = "given"
        references = _load(Reference.objects.filter(author=user), user, tab)
    else:
        tab = "received"
        references = _load(references_about(user), user, tab, holder=user)
    # Only skills tagged on references about you (or your community) wait for *your* confirmation
    pending = [
        tag for reference in references
        for tag in reference.visible_skill_tags if tag.status == ReferenceSkill.STATUS_PENDING
    ] if tab != "given" else []
    return render(request, "references/references_list.html", {
        "tab": tab,
        "community": community,
        "header_photo": next(iter(community.photos.all()), None) if community else None,
        "references": references,
        "pending_tags": pending,
    })
