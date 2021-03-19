from django.shortcuts import render, get_object_or_404

from .models import Community


def detail(request, slug):
    """Show Community page"""
    community = get_object_or_404(Community, slug=slug)
    return render(request, "communities/community_detail.html", {"community": community})
