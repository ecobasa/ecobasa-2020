from django.db.models import Prefetch
from django.shortcuts import render

from references.models import Reference, ReferenceSkill

HOMEPAGE_REFERENCES = 6


def homepage(request):
    # References staff featured (from those their authors agreed to share), newest first
    featured = (
        Reference.objects.filter(share_publicly=True, featured_at__isnull=False)
        .select_related("author", "content_type")
        .prefetch_related("subject", Prefetch("skill_tags", queryset=ReferenceSkill.objects.select_related("skill")))
        .order_by("-featured_at")[:HOMEPAGE_REFERENCES]
    )
    return render(request, "homepage/homepage.html", {"featured_references": featured})

def support(request):
    return render(request, "homepage/support.html")