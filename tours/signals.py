from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from communities.models import Community
from gift_economy.matches.models import Match


@receiver(post_save, sender=Community)
def rebuild_routes_through(sender, instance, **kwargs):
    """A community's place or whether it is public changed: the routes of tours that stop
    there (also at its events) go through its new public point (plan 5.5, rule 7)."""
    from .models import Tour

    for tour in Tour.objects.filter(stops__community=instance).distinct():
        tour.rebuild_route()


# ── Tour visits follow the travellers and the agreed days ───────────
# After the transaction: a stop that moves saves twice, an accept saves the match and
# its message. Syncing is idempotent, so running it more than once does no harm.
def _sync_later(tour_id):
    if tour_id is None:
        return

    def run():
        from .models import Tour
        from .visits import sync_visits

        tour = Tour.objects.filter(pk=tour_id).first()
        if tour is not None:
            sync_visits(tour)

    transaction.on_commit(run)


@receiver(post_save, sender=Match)
def match_changed(sender, instance, **kwargs):
    from .visits import follow_agreed_days

    traveller = getattr(instance, "traveller", None)
    if traveller is not None:
        _sync_later(traveller.tour_id)
    if getattr(instance, "tour_stop", None) is not None:
        follow_agreed_days(instance)


@receiver([post_save, post_delete], sender="tours.Traveller")
@receiver([post_save, post_delete], sender="tours.Stop")
def route_or_travellers_changed(sender, instance, **kwargs):
    _sync_later(instance.tour_id)
