"""Shortcuts for tests: the offers and wishes that used to be skills, skill wishes and
event needs, made the way the forms make them."""

from .models import Listing, _holder_fields, wish_kind_for


def skill_offer(holder, skill, **fields):
    """A person's or community's skill (in a event with event=…)."""
    if "event" in fields:
        holder = fields["event"].community
    return Listing.objects.create(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill=skill,
                                  **_holder_fields(holder), **fields)


def skill_wish(holder, skill, **fields):
    """A person wants to learn a skill; a community looks for people with it."""
    return Listing.objects.create(type=Listing.TYPE_WISH, kind=fields.pop("kind", wish_kind_for(holder)), skill=skill,
                                  **_holder_fields(holder), **fields)


def need(event, title, kind=Listing.KIND_HANDS, category=None, **fields):
    """One thing a event needs: the community's wish in it."""
    listing = Listing.objects.create(type=Listing.TYPE_WISH, kind=kind, title=title, event=event, **fields)
    if category is not None:
        listing.categories.add(category)
    return listing
