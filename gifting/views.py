from django.shortcuts import render, get_object_or_404

from .models import Ad
from .filters import AdFilter


def search(request):
    f = AdFilter(request.GET, queryset=Ad.objects.all())
    return render(request, "gifting/search.html", {"ads": f.qs, "f": f})


def detail(request, pk):
    ad = get_object_or_404(Ad, pk=pk)
    return render(request, "gifting/ad_detail.html", {"ad": ad})
