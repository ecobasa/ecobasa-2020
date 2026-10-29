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
    """Which lending calendars the dashboard shows: their own once someone lends something
    or borrows something, and one for each community they are ambassador of that lends
    things (its tool library). Lazy, so pages that don't show them don't query them."""
    def own():
        if not request.user.is_authenticated:
            return False
        from gift_economy.gifts.models import Listing
        from .models import Loan
        return (
            Listing.objects.of(request.user).to_lend().exists()
            or Loan.objects.filter(match__from_user=request.user).exists()
        )

    def communities():
        if not request.user.is_authenticated:
            return []
        from gift_economy.gifts.models import Listing
        lending = Listing.objects.to_lend().filter(community__owner=request.user).values("community")
        return list(request.user.communities.filter(pk__in=lending).order_by("name"))

    return {
        "has_lending_calendar": SimpleLazyObject(own),
        "lending_communities": SimpleLazyObject(communities),
    }
