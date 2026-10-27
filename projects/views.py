from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from communities.models import Community
from dashboard_lists import Choice, paginate, query_url
from matches.emails import notify_match_created
from matches.models import Match, VolunteerDetails
from skills.models import skill_name_q

from .forms import HelpOfferForm, NeedFormSet, ProjectForm
from .freshness import read_confirm_token
from .models import Need, NeedOffer, Project

_NEEDS = Prefetch(
    "needs", queryset=Need.objects.select_related("skill", "category").prefetch_related("need_offers__match__from_user"),
)


def _projects():
    return Project.objects.select_related("community", "community__owner").prefetch_related(_NEEDS)


def project_list(request):
    """Projects of all communities, freshest first: the current ones, or the archived
    (and ended) ones. Filtered by a search and by the kind of need."""
    archived = request.GET.get("show") == "archived"
    projects = _projects()
    current = projects.current()
    projects = projects.exclude(pk__in=current) if archived else current
    q = (request.GET.get("q") or "").strip()
    if q:
        projects = projects.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(community__name__icontains=q)
            | Q(community__location_name__icontains=q)
            | Q(needs__title__icontains=q)
            | skill_name_q(q, "needs__skill__")
        ).distinct()
    # Current projects by the kind of their open needs, archived ones by any of their needs
    def of_kind(kind):
        return projects.filter(needs__kind=kind, **({} if archived else {"needs__covered_at": None})).distinct()

    kind = request.GET.get("kind", "")
    shows = [
        Choice(label, query_url(request, show=key, page=None), archived == (key == "archived"), count, icon=icon)
        for key, label, icon, count in (
            (None, _("Current"), "fa-person-digging", current.count()),
            ("archived", _("Archived"), "fa-box-archive", _projects().exclude(pk__in=current).count()),
        )
    ]
    kinds = [Choice(_("All"), query_url(request, kind=None, page=None), not kind, projects.count())] + [
        Choice(label, query_url(request, kind=value, page=None), kind == value, of_kind(value).count(), icon=Need.KIND_ICONS[value])
        for value, label in Need.KIND_CHOICES
    ]
    if kind in dict(Need.KIND_CHOICES):
        projects = of_kind(kind)
    page = paginate(request, projects)
    return render(request, "projects/project_list.html", {
        "page": page,
        "projects": page.object_list,
        "q": q,
        "archived": archived,
        "shows": shows,
        "kinds": kinds,
    })


def detail(request, pk):
    project = get_object_or_404(_projects(), pk=pk)
    can_edit = project.can_edit(request.user)
    if project.archived_at and not can_edit:
        messages.info(request, _("This project has been archived."))
    offers = []
    if can_edit:
        offers = list(
            project.matches.select_related("from_user").prefetch_related("need_offers__need__skill")
            .exclude(status=Match.STATUS_DECLINED)
        )
    return render(request, "projects/project_detail.html", {
        "project": project,
        "community": project.community,
        "needs": list(project.needs.all()),
        "can_edit": can_edit,
        "offers": offers,
        "own_offer": (
            project.matches.filter(from_user=request.user).exclude(status=Match.STATUS_DECLINED).first()
            if request.user.is_authenticated else None
        ),
    })


def _save_project(request, project, template_context):
    form = ProjectForm(request.POST or None, instance=project)
    formset = NeedFormSet(request.POST or None, instance=project, prefix="needs")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            project = form.save(commit=False)
            if not project.pk:
                project.created_by = request.user
            project.touch(save=False)
            project.save()
            formset.instance = project
            formset.save(commit=False)
            for need in formset.deleted_objects:
                need.delete()
            # Keep the needs in the order they were entered
            kept = [f for f in formset.forms if f.has_changed() or f.instance.pk]
            for order, need_form in enumerate(f for f in kept if f not in formset.deleted_forms):
                need = need_form.save(commit=False)
                need.project = project
                need.order = order
                need.save()
        messages.success(request, _("The project has been saved."))
        return redirect(project.get_absolute_url())
    return render(request, "projects/project_form.html", {
        **template_context, "form": form, "formset": formset,
    })


@login_required
def create(request, community_slug):
    community = get_object_or_404(Community, slug=community_slug)
    if not (request.user.is_staff or request.user == community.owner):
        raise PermissionDenied
    return _save_project(request, Project(community=community), {"community": community})


@login_required
def edit(request, pk):
    project = get_object_or_404(Project.objects.select_related("community"), pk=pk)
    if not project.can_edit(request.user):
        raise PermissionDenied
    return _save_project(request, project, {"community": project.community, "project": project})


@login_required
@require_POST
def archive(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not project.can_edit(request.user):
        raise PermissionDenied
    project.archived_at = timezone.now()
    project.save(update_fields=["archived_at"])
    messages.success(request, _("The project has been archived. You can bring it back at any time."))
    return redirect(project.community.get_absolute_url())


@login_required
@require_POST
def confirm(request, pk):
    """The ambassador says the project is still current (also brings back an archived one
    that hasn't ended)."""
    project = get_object_or_404(Project, pk=pk)
    if not project.can_edit(request.user):
        raise PermissionDenied
    if project.is_over:
        messages.error(request, _("This project has ended. Change its dates to bring it back."))
        return redirect("projects:edit", pk=project.pk)
    project.touch()
    messages.success(request, _("Thanks! The project shows as up to date again."))
    return redirect(project.get_absolute_url())


def confirm_by_email(request, token):
    """One click from the "Is this still current?" email, no login needed."""
    try:
        pk = read_confirm_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid or expired link.")
    project = get_object_or_404(Project, pk=pk)
    if project.is_over:
        messages.error(request, _("This project has ended. Change its dates to bring it back."))
    else:
        project.touch()
        messages.success(request, _("Thanks! The project shows as up to date again."))
    return redirect(project.get_absolute_url())


@login_required
@require_POST
def toggle_need(request, pk, need_pk):
    """Mark a need as covered (however it was covered), or open it again."""
    project = get_object_or_404(Project, pk=pk)
    if not project.can_edit(request.user):
        raise PermissionDenied
    need = get_object_or_404(project.needs, pk=need_pk)
    need.covered_at = None if need.covered_at else timezone.now()
    need.save(update_fields=["covered_at"])
    project.touch()
    return redirect(project.get_absolute_url())


@login_required
def offer_help(request, pk):
    project = get_object_or_404(_projects(), pk=pk)
    community = project.community
    if not project.is_current or community.owner is None:
        messages.error(request, _("This project doesn't take offers at the moment."))
        return redirect(project.get_absolute_url())
    if request.user == community.owner:
        return redirect(project.get_absolute_url())

    form = HelpOfferForm(project, request.POST or None, preselected=request.GET.getlist("need"))
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            match = Match(from_user=request.user, recipient=project.get_match_owner(), message=form.cleaned_data["message"])
            match.target = project
            match.save()
            VolunteerDetails.objects.create(
                match=match,
                volunteer_mode="wish",
                stay_from=_day_start(form.cleaned_data["stay_from"]),
                stay_to=_day_start(form.cleaned_data["stay_to"]),
            )
            for need, quantity in form.chosen_needs():
                NeedOffer.objects.create(need=need, match=match, quantity=quantity)
        notify_match_created(match, http_request=request)
        messages.success(request, _("Your offer has been sent to %(community)s!") % {"community": community.name})
        return redirect(match.get_absolute_url())

    return render(request, "projects/offer_help.html", {
        "project": project, "community": community, "form": form,
    })


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min)) if day else None

