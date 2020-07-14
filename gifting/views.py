from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator

from .models import Ad
from .filters import AdFilter
from .forms import AdForm


def search(request):
    """Show all ads with filter ability"""
    f = AdFilter(request.GET, queryset=Ad.objects.all())

    # pagination
    paginator = Paginator(f.qs, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "gifting/search.html", {"page_obj": page_obj, "f": f})


def detail(request, pk):
    """Show details for an Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    return render(request, "gifting/ad_detail.html", {"ad": ad})


def create(request):
    """Create a new Ad"""
    form = AdForm()
    if request.method == "POST":
        form = AdForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifting/ad_form.html", {"form": form})


def edit(request, pk):
    """Edit an existing Ad"""
    ad = get_object_or_404(Ad, pk=pk)
    form = AdForm(instance=ad)
    if request.method == "POST":
        form = AdForm(request.POST, instance=ad)
        if form.is_valid():
            form.save()
            return redirect(form.instance.get_absolute_url())
    return render(request, "gifting/ad_form.html", {"form": form, "ad": ad})
