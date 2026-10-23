from django.utils.functional import SimpleLazyObject


def pending_reference_skills(request):
    """Number of skills tagged on references about you that wait for your confirmation,
    for the dashboard sidebar. Lazy, so pages that don't show it don't query it."""
    def count():
        if not request.user.is_authenticated:
            return 0
        from .models import ReferenceSkill, references_received
        return ReferenceSkill.objects.filter(
            status=ReferenceSkill.STATUS_PENDING, reference__in=references_received(request.user)
        ).count()
    return {"pending_reference_skills": SimpleLazyObject(count)}
