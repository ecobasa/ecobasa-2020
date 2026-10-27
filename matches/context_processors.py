from django.utils.functional import SimpleLazyObject


def new_suggestions(request):
    """How many suggestions they haven't looked at yet, for the menus. Lazy, so pages that
    don't show it don't query it."""
    def count():
        if not request.user.is_authenticated:
            return 0
        return request.user.suggestions.filter(seen_at=None, dismissed_at=None).count()

    return {"new_suggestions_count": SimpleLazyObject(count)}
