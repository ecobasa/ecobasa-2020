from django.utils.functional import SimpleLazyObject


def new_suggestions(request):
    """How many suggestions they haven't looked at yet, for the menus. Lazy, so pages that
    don't show it don't query it."""
    def count():
        if not request.user.is_authenticated:
            return 0
        return request.user.suggestions.filter(seen_at=None, dismissed_at=None).count()

    return {"new_suggestions_count": SimpleLazyObject(count)}


def lending_calendar(request):
    """Whether the dashboard shows the lending calendar: once someone offers a tool to
    lend, or borrows one. Lazy, so pages that don't show it don't query it."""
    def shown():
        if not request.user.is_authenticated:
            return False
        from gift_economy.gifts.models import Listing
        from .models import Loan
        return (
            Listing.objects.managed_by(request.user).to_lend().exists()
            or Loan.objects.filter(match__from_user=request.user).exists()
        )

    return {"has_lending_calendar": SimpleLazyObject(shown)}
