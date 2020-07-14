from django.core.paginator import Paginator

from .models import Ad
from .filters import AdFilter


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
