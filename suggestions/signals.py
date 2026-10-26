"""Match right after something matchable is saved, once the request's transaction is
committed, and forget its suggestions when it is deleted."""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save

from gifts.models import Listing
from projects.models import Need
from skills.models import CommunitySkill, SkillWish, UserSkill

from . import engine

logger = logging.getLogger(__name__)

MATCHED_MODELS = (Listing, Need, UserSkill, CommunitySkill, SkillWish)


def schedule_match(obj):
    model, pk = type(obj), obj.pk

    def run():
        fresh = model.objects.filter(pk=pk).first()
        if fresh is None:
            return
        try:
            engine.match(fresh)
        except Exception:  # matching must never break saving what people wrote
            logger.exception("Matching %s %s failed", model.__name__, pk)

    transaction.on_commit(run)


def _saved(sender, instance, raw=False, **kwargs):
    if not raw:
        schedule_match(instance)


def _deleted(sender, instance, **kwargs):
    engine.forget(instance)


for _model in MATCHED_MODELS:
    post_save.connect(_saved, sender=_model, dispatch_uid=f"suggestions-match-{_model.__name__}")
    post_delete.connect(_deleted, sender=_model, dispatch_uid=f"suggestions-forget-{_model.__name__}")

