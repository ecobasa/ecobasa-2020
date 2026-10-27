from django.utils.functional import SimpleLazyObject


def new_suggestions(request):
    """How many suggestions they haven't looked at yet, in all and per kind of match, for
    the menus. Lazy, so pages that don't show them don't query them."""
    from .models import suggestions_of_kind

    def unseen():
        return request.user.suggestions.filter(seen_at=None, dismissed_at=None)

    def count():
        return unseen().count() if request.user.is_authenticated else 0

    def by_kind():
        if not request.user.is_authenticated:
            return {}
        return {kind: suggestions_of_kind(unseen(), kind).count() for kind in ("gift", "skills", "volunteer")}

    return {
        "new_suggestions_count": SimpleLazyObject(count),
        "new_suggestions_by_kind": SimpleLazyObject(by_kind),
    }
