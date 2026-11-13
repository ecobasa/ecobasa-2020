import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from communities.models import Community
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import STAY_APP_LABELS, Match

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Community)
def rebuild_routes_through(sender, instance, **kwargs):
    """A community's place or whether it is public changed: the routes of tours that stop
    there (also at its events) go through its new public point."""
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
    _suggest_tour_later(instance.tour_id)


# ── A tour's needs are matched along its route ──────────────────────
@receiver(post_save, sender="tours.Tour")
def tour_saved(sender, instance, raw=False, **kwargs):
    """Its route, dates or whether it is published or listed changed: what it looks for
    is matched again (only where it is current, matching.side_of)."""
    from gift_economy.matches.signals import schedule_match

    if raw:
        return
    for need in instance.listings.filter(type="wish"):
        schedule_match(need)
    _suggest_tour_later(instance.pk)


# ── Tours are suggested to the people they fit ──────────────────────
# After the transaction, once per tour or person however often it saved. Suggesting
# must never break saving what people wrote.
_pending_tours, _pending_people = set(), set()


def _suggest_tour_later(tour_id):
    if tour_id is None or tour_id in _pending_tours:
        return
    _pending_tours.add(tour_id)

    def run():
        from .matching import suggest_tour
        from .models import Tour

        _pending_tours.discard(tour_id)
        tour = Tour.objects.filter(pk=tour_id).first()
        if tour is None:
            return
        try:
            suggest_tour(tour)
        except Exception:
            logger.exception("Suggesting tour %s failed", tour_id)

    transaction.on_commit(run)


def _suggest_for_later(user_id):
    if user_id is None or user_id in _pending_people:
        return
    _pending_people.add(user_id)

    def run():
        from django.contrib.auth import get_user_model

        from .matching import suggest_for

        _pending_people.discard(user_id)
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return
        try:
            suggest_for(user)
        except Exception:
            logger.exception("Suggesting tours to user %s failed", user_id)

    transaction.on_commit(run)


@receiver(post_save, sender="tours.Traveller")
def asked_to_join(sender, instance, raw=False, **kwargs):
    """Who asked to join (or was invited) needn't be told about the tour any more."""
    from .matching import forget_tour

    if not raw:
        forget_tour(instance.tour, instance.user)


@receiver(post_save, sender=Match)
def stay_changed(sender, instance, raw=False, **kwargs):
    """A stay at a community or event: tours that go there around its days are
    suggested; once it is declined or withdrawn, no longer."""
    from .matching import forget_stay

    if raw or instance.content_type.app_label not in STAY_APP_LABELS or getattr(instance, "tour_stop", None):
        return
    if instance.is_closed:
        forget_stay(instance)
    else:
        _suggest_for_later(instance.from_user_id)
        _suggest_together_later(instance.pk)


def _suggest_together_later(stay_id):
    def run():
        from .matching import suggest_together

        stay = Match.objects.filter(pk=stay_id).select_related("from_user", "content_type").first()
        if stay is None:
            return
        try:
            suggest_together(stay)
        except Exception:
            logger.exception("Suggesting who comes along to stay %s failed", stay_id)

    transaction.on_commit(run)


@receiver(post_save, sender=Listing)
def listing_saved(sender, instance, raw=False, **kwargs):
    """Someone's offer or wish (a thing, or a skill to learn): the tours that fit it now
    are suggested to them. A host's offer or wish: to the people it fits on the tours
    that stop there."""
    from .models import Tour

    if raw or instance.tour_id:
        return
    if instance.community_id:
        if instance.kind in Listing.THING_KINDS:
            for tour_id in Tour.objects.current().filter(stops__community=instance.community_id).values_list("pk", flat=True).distinct():
                _suggest_tour_later(tour_id)
    elif instance.owner_id and (instance.kind in Listing.THING_KINDS or (instance.is_wish and instance.kind == Listing.KIND_SKILL)):
        _suggest_for_later(instance.owner_id)
