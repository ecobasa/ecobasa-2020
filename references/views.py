from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _, pgettext
from django.views.decorators.http import require_POST

from dashboard_lists import Choice, paginate, query_url

from .forms import ReferenceForm, form_context
from .models import Reference, ReferenceSkill, is_referenceable, references_about, match_gift_names, match_reference_subject, match_skill_names, subject_owner
from .notifications import notify_reference_created
from .reference_requests import exchange_context, existing_reference, find_reference_request, subject_name


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
    form = ReferenceForm(request.POST, request.FILES, instance=existing, subject=subject)
    if form.is_valid():
        reference = form.save_reference(request.user, subject)
        if existing is None:
            notify_reference_created(reference, http_request=request)
        messages.success(request, _("Thank you for sharing your experience."))
    elif "photo" in form.errors:
        messages.error(request, form.errors["photo"][0])
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
    """Dashboard: references received (about you, your listings and skills) and given
    (by you) as two tabs, or those about a community you are ambassador of
    (?community=<slug>). A community can't write references itself, so its references
    are a page of their own."""
    user = request.user
    community = None
    tabs = []
    if request.GET.get("community"):
        community = get_object_or_404(user.communities.prefetch_related("photos"), slug=request.GET["community"])
        tab = "community"
        references = _load(references_about(community), user, "received", holder=community)
    else:
        tab = "given" if request.GET.get("type") == "given" else "received"
        received = references_about(user)
        given = Reference.objects.filter(author=user)
        tabs = [
            Choice(_("Received"), query_url(request, type=None), tab == "received", received.count(),
                   ReferenceSkill.objects.filter(status=ReferenceSkill.STATUS_PENDING, reference__in=received).count()),
            Choice(pgettext("references", "Given"), query_url(request, type="given"), tab == "given", given.count()),
        ]
        references = _load(given, user, tab) if tab == "given" else _load(received, user, tab, holder=user)
    # Only skills tagged on references about you (or your community) wait for *your* confirmation
    pending = [
        tag for reference in references
        for tag in reference.visible_skill_tags if tag.status == ReferenceSkill.STATUS_PENDING
    ] if tab != "given" else []
    return render(request, "references/references_list.html", {
        "tab": tab,
        "tabs": tabs,
        "community": community,
        "header_photo": next(iter(community.photos.all()), None) if community else None,
        "page": paginate(request, references),
        "pending_tags": pending,
    })


def reference_request(request, key):
    """The reference form from the email after a match. The key is the login: it works from
    a phone's mail app without signing in."""
    reference_request = find_reference_request(key)
    if reference_request is None:
        return render(request, "references/request_expired.html", status=404)
    match, user = reference_request.match, reference_request.user
    subject, gift, skill = match_reference_subject(match, user)
    reference = existing_reference(reference_request)
    if request.method == "POST":
        form = ReferenceForm(request.POST, request.FILES, instance=reference, subject=subject, story=True)
        if form.is_valid():
            saved = form.save_reference(user, subject, match=match)
            reference_request.reference = saved
            reference_request.save(update_fields=["reference"])
            if reference is None:
                notify_reference_created(saved, http_request=request)
            return render(request, "references/request_thanks.html", {
                "subject": subject, "shared": saved.share_publicly,
            })
    else:
        form = ReferenceForm(instance=reference, subject=subject, story=True, initial={
            # From the email after a reply: "allow sharing" comes pre-ticked
            **({"share_publicly": True} if request.GET.get("share") else {}),
        })
        skills = [name for name in [skill, *match_skill_names(match, user)] if name]
        if form.can_tag and skills:
            # What the match was about is filled in; they can change it
            field = form.fields["skill_names"]
            names = [n.strip() for n in (field.initial or "").split(",") if n.strip()]
            field.initial = ", ".join([*names, *(name for name in skills if name not in names)])
    return render(request, "references/request_form.html", {
        **form_context(subject, form, reference, [gift, *match_gift_names(match, user)]),
        "subject": subject,
        "subject_name": subject_name(subject),
        **exchange_context(match, user),
        "reference_request": reference_request,
    })


@staff_member_required
def featured(request):
    """Staff pick the references shown on the homepage, from those their authors agreed to
    share. Made to work on a phone."""
    if request.method == "POST":
        reference = get_object_or_404(Reference, pk=request.POST.get("reference"), share_publicly=True)
        reference.featured_at = timezone.now() if request.POST.get("action") == "feature" else None
        reference.save(update_fields=["featured_at"])
        return redirect(f"{request.path}#reference-{reference.pk}")
    shared = (
        Reference.objects.filter(share_publicly=True)
        .select_related("author", "content_type")
        .prefetch_related("subject", Prefetch("skill_tags", queryset=ReferenceSkill.objects.select_related("skill")))
        .order_by("featured_at", "-created_at")
    )
    return render(request, "references/featured.html", {
        "featured": sorted((r for r in shared if r.featured_at), key=lambda r: r.featured_at, reverse=True),
        "candidates": [r for r in shared if not r.featured_at and r.impression == Reference.IMPRESSION_POSITIVE],
        "others": [r for r in shared if not r.featured_at and r.impression != Reference.IMPRESSION_POSITIVE],
    })
