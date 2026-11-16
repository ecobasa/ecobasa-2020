from django.utils.functional import SimpleLazyObject


def waiting(request):
    """What waits for their answer, by page (views.waiting_counts), for the badges in the
    menus. Lazy, so pages that don't show them don't query them."""
    def counts():
        if not request.user.is_authenticated:
            return {}
        from .views import waiting_counts
        return waiting_counts(request.user)

    return {"waiting": SimpleLazyObject(counts)}


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
        lending = Listing.objects.to_lend().filter(community__ambassador=request.user).values("community")
        return list(request.user.ambassador_of.filter(pk__in=lending).order_by("name"))

    return {
        "has_lending_calendar": SimpleLazyObject(own),
        "lending_communities": SimpleLazyObject(communities),
    }


def sent_requests(request):
    """Whether they ever asked for a volunteer visit, to become a member of a community,
    or came to an event, for the menu entries that list them. Lazy, so pages that don't
    show them don't query them."""
    def sent(q):
        def any_():
            if not request.user.is_authenticated:
                return False
            return Match.objects.filter(q, from_user=request.user).exists()
        return SimpleLazyObject(any_)

    from django.db.models import Q
    from .models import Match, stay_q
    return {
        "has_volunteer_visits": sent(stay_q()),
        "has_membership_applications": sent(Q(content_type__app_label="communities", content_type__model="membership")),
        "attends_events": sent(Q(
            content_type__app_label="events", content_type__model="event", status=Match.STATUS_ACCEPTED,
        )),
    }
