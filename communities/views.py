from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import Community
from .models import CommunityPhoto
from .forms import CommunityForm


def index(request):
    """Map-first list of communities."""
    # base queryset (used to derive country options)
    base_qs = Community.objects.all().prefetch_related("photos", "skills").order_by("name")

    # compute available countries from location_name (last comma-separated part)
    countries = sorted({
        loc.split(',')[-1].strip()
        for loc in base_qs.values_list('location_name', flat=True)
        if loc
    })

    communities = base_qs
    q = (request.GET.get("q") or "").strip()
    if q:
        communities = communities.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(location_name__icontains=q)
            | Q(skills__name__icontains=q)
        ).distinct()
    # optional country filter
    country = (request.GET.get('country') or '').strip()
    if country:
        communities = communities.filter(location_name__icontains=country)

    map_communities = []
    for c in communities:
        if not c.location:
            continue
        first_photo = c.photos.first()
        photo_url = first_photo.image.url if first_photo and first_photo.image else None
        map_communities.append(
            {
                "name": c.name,
                "slug": c.slug,
                "type": c.get_type_display(),
                "status": c.get_status_display(),
                "description": c.description,
                "location_name": c.location_name,
                "lat": c.location.y,
                "lon": c.location.x,
                "url": reverse("communities:detail", kwargs={"slug": c.slug}),
                "image": photo_url,
                "members": c.inhabitants,
                "children": c.children,
                "visitors": c.max_guests,
                "skills": [s.name for s in c.skills.all()],
            }
        )

    return render(
        request,
        "communities/community_list.html",
        {
            "communities": communities,
            "map_communities": map_communities,
            "q": q,
            "countries": countries,
            "selected_country": country,
        },
    )


def detail(request, slug):
    """Show Community page"""
    community = get_object_or_404(Community, slug=slug)
    photos = list(community.photos.all())
    hero_image = photos[0].image.url if photos else None
    return render(request, "communities/community_detail.html", {
        "community": community,
        "photos": photos,
        "hero_image": hero_image,
    })


def _collect_gallery_files(form, request):
    images = []
    cleaned = form.cleaned_data.get("gallery")
    if cleaned:
        if isinstance(cleaned, (list, tuple)):
            images.extend(cleaned)
        else:
            images.append(cleaned)
    # also read raw FILES to be safe with multi-file widgets
    for f in request.FILES.getlist("gallery"):
        if f not in images:
            images.append(f)
    return images


def create(request):
    """Public community submission form."""
    if request.method == "POST":
        form = CommunityForm(request.POST, request.FILES)
        if form.is_valid():
            community = form.save(commit=False)
            if request.user.is_authenticated:
                community.owner = request.user
            community.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            images = _collect_gallery_files(form, request)
            for image_file in images:
                CommunityPhoto.objects.create(community=community, image=image_file)
            if images:
                messages.success(request, _("Uploaded %(count)s image(s).") % {"count": len(images)})
            return redirect(community.get_absolute_url())
        else:
            messages.error(
                request,
                _("Form invalid: %(errors)s")
                % {"errors": "; ".join([f"{k}: {','.join(v)}" for k, v in form.errors.items()])},
            )
    else:
        form = CommunityForm()

    return render(
        request,
        "communities/community_form.html",
        {"form": form},
    )

def update(request, slug):
    community = get_object_or_404(Community, slug=slug)
    if not request.user.is_authenticated or (community.owner and request.user != community.owner and not request.user.is_staff):
        return redirect(community.get_absolute_url())

    if request.method == "POST":
        form = CommunityForm(request.POST, request.FILES, instance=community)
        if form.is_valid():
            community = form.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            delete_ids = request.POST.getlist("delete_photos")
            if delete_ids:
                community.photos.filter(id__in=delete_ids).delete()
            images = _collect_gallery_files(form, request)
            for image_file in images:
                CommunityPhoto.objects.create(community=community, image=image_file)
            if images:
                messages.success(request, _("Uploaded %(count)s image(s).") % {"count": len(images)})
            messages.success(request, _("Community updated."))
            return redirect(community.get_absolute_url())
        else:
            messages.error(
                request,
                _("Form invalid: %(errors)s")
                % {"errors": "; ".join([f"{k}: {','.join(v)}" for k, v in form.errors.items()])},
            )
    else:
        form = CommunityForm(instance=community)

    return render(
        request,
        "communities/community_form.html",
        {"form": form, "community": community},
    )
