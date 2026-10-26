from django.utils.functional import SimpleLazyObject


def pending_reference_skills(request):
    """For the dashboard sidebar: how many skills tagged on references about you wait for
    your confirmation, and the same per community you are ambassador of. Lazy, so pages
    that don't show the sidebar don't query it."""
    from .models import ReferenceSkill, references_about

    def pending_count(subject):
        return ReferenceSkill.objects.filter(
            status=ReferenceSkill.STATUS_PENDING, reference__in=references_about(subject)
        ).count()

    def own():
        return pending_count(request.user) if request.user.is_authenticated else 0

    def communities():
        if not request.user.is_authenticated:
            return []
        return [
            {"community": community, "pending": pending_count(community)}
            for community in request.user.communities.order_by("name")
        ]

    return {
        "pending_reference_skills": SimpleLazyObject(own),
        "reference_communities": SimpleLazyObject(communities),
    }
