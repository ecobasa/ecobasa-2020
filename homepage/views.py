from django.shortcuts import render

from gift_economy.references.models import Reference, with_card_data

HOMEPAGE_REFERENCES = 3


def homepage(request):
    # A different few each visit of the references staff featured (from those their
    # authors agreed to share)
    featured = with_card_data(
        Reference.objects.filter(share_publicly=True, pending=False, featured_at__isnull=False)
    ).order_by("?")[:HOMEPAGE_REFERENCES]
    return render(request, "homepage/homepage.html", {"featured_references": featured})

def support(request):
    return render(request, "homepage/support.html")