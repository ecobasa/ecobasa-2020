from django.db.models import Q
from django.utils.functional import SimpleLazyObject


def on_tours(request):
    """Whether they organise, travel on or asked to join a tour, for the "Your tours"
    menu entry. Lazy, so pages that don't show it don't query it."""
    def any_():
        if not request.user.is_authenticated:
            return False
        from gift_economy.matches.models import Match

        return request.user.tour_travels.filter(
            Q(match=None) | ~Q(match__status__in=Match.CLOSED_STATUSES),
        ).exists()

    return {"on_tours": SimpleLazyObject(any_)}
