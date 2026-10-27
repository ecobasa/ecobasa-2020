from django.shortcuts import render

from references.models import Reference, with_card_data

HOMEPAGE_REFERENCES = 6


def homepage(request):
    # References staff featured (from those their authors agreed to share), newest first
    featured = with_card_data(
        Reference.objects.filter(share_publicly=True, featured_at__isnull=False)
    ).order_by("-featured_at")[:HOMEPAGE_REFERENCES]
    return render(request, "homepage/homepage.html", {"featured_references": featured})

def support(request):
    return render(request, "homepage/support.html")