from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.core.paginator import Paginator
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required

from .models import Ad
from .filters import AdFilter
from .forms import AdForm


def search(request):
    """Show all ads with filter ability"""
    f = AdFilter(request.GET, queryset=Ad.objects.all(), request=request)

    # pagination
    paginator = Paginator(f.qs, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "gifting/search.html", {"page_obj": page_obj, "f": f})


def detail(request, pk):
    """Show details for an Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    return render(request, "gifting/ad_detail.html", {"ad": ad})


@login_required
def create(request):
    """Create a new Ad"""
    form = AdForm()
    if request.method == "POST":
        form = AdForm(request.POST, request.FILES)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.owner = request.user
            form.save()
            messages.success(
                request, _("%(ad_type)s created") % {"ad_type": ad.get_type_display()}
            )
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifting/ad_form.html", {"form": form})


def edit(request, pk):
    """Edit an existing Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    if not ad.owner == request.user:
        return redirect("/users/login?next=%s" % request.path)

    form = AdForm(instance=ad)
    if request.method == "POST":
        form = AdForm(request.POST, request.FILES, instance=ad)
        if form.is_valid():
            form.save()
            ad = form.instance
            messages.success(request, _("changes saved"))
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifting/ad_form.html", {"form": form, "ad": ad})


def delete(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    if not ad.owner == request.user:
        return redirect("/users/login?next=%s" % request.path)

    if request.method == "POST":
        ad.delete()
        messages.success(
            request, _("%(ad_type)s deleted") % {"ad_type": ad.get_type_display()}
        )
        return redirect(reverse("gifting:search"))
    else:
        return render(request, "gifting/ad_delete_confirm.html", {"ad": ad})
