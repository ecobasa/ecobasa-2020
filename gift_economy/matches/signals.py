"""Match right after something matchable is saved, once the request's transaction is
committed, and forget its suggestions when it is deleted. When a person or community
moves (place or country), everything that takes its place from them is matched again."""

import logging

from django.db import transaction
from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save, pre_save

from communities.models import Community

from gift_economy.gifts.models import Listing

from . import matching

logger = logging.getLogger(__name__)

MATCHED_MODELS = (Listing,)


def schedule_match(obj):
    model, pk = type(obj), obj.pk

    def run():
        fresh = model.objects.filter(pk=pk).first()
        if fresh is None:
            return
        try:
            matching.match(fresh)
        except Exception:  # matching must never break saving what people wrote
            logger.exception("Matching %s %s failed", model.__name__, pk)

    transaction.on_commit(run)


def _saved(sender, instance, raw=False, **kwargs):
    if not raw:
        schedule_match(instance)


def _deleted(sender, instance, **kwargs):
    matching.forget(instance)


for _model in MATCHED_MODELS:
    post_save.connect(_saved, sender=_model, dispatch_uid=f"matches-match-{_model.__name__}")
    post_delete.connect(_deleted, sender=_model, dispatch_uid=f"matches-forget-{_model.__name__}")


# ── Moving ────────────────────────────────────────────────────────────

def _remember_location(sender, instance, raw=False, **kwargs):
    instance._place_before = (
        None if raw or instance.pk is None
        else sender.objects.filter(pk=instance.pk).values_list("location", "country").first()
    )


def _moved(instance):
    """Whether their place or country changed in this save."""
    before = getattr(instance, "_place_before", None)
    if before is None:
        return False
    location, country = before
    if str(country or "") != str(instance.country or ""):
        return True
    now = instance.location
    if location is None or now is None:
        return (location is None) != (now is None)
    return not location.equals_exact(now, 1e-6)


def _user_saved(sender, instance, raw=False, created=False, **kwargs):
    if raw or created or not _moved(instance):
        return
    # All their offers and wishes: a listing's country is its owner's
    for obj in Listing.objects.of(instance):
        schedule_match(obj)


def _community_saved(sender, instance, raw=False, created=False, **kwargs):
    if raw or created or not _moved(instance):
        return
    for obj in Listing.objects.of(instance).current():
        schedule_match(obj)


for _model, _handler in ((get_user_model(), _user_saved), (Community, _community_saved)):
    pre_save.connect(_remember_location, sender=_model, dispatch_uid=f"matches-location-{_model.__name__}")
    post_save.connect(_handler, sender=_model, dispatch_uid=f"matches-moved-{_model.__name__}")
