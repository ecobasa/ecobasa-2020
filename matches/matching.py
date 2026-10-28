"""The matching: when an offer or a wish (gifts.Listing) is saved, find what fits it
nearby and suggest the pair to both sides.

What fits, an offer and a wish:
- with a skill (a skill, or knowledge or helping hands with a known skill): the same
  skill, in any language;
- without one, things (or knowledge or helping hands named in words) with a similar
  title ("Clay" ~ "Clay from our pond", "Scythe" ~ "Two old scythes"). A material doesn't
  fit a tool; "other" fits any thing. Not by gift category alone: firewood and a chimney
  pipe can both be for building, but neither helps with the other.

Where each side looks, by their owner's settings (reaches()):
- with a place: within their distance (User.match_radius);
- with only a country: in that country;
- with neither: anywhere, as with "search worldwide" (User.match_global).
Nothing is suggested between things of the same person (or community), for skills that
aren't available, or for what is covered, given away or part of a project that is over."""

import math
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.measure import D
from django.db.models import Q

from gifts.models import Listing

from .models import Suggestion

# Upper bound for anyone's distance; candidates with a place are looked up within it, then
# each side's own settings decide
MAX_RADIUS_KM = 2000

# The places a listing can have: its own, its person's, its community's
PLACES = ("location", "owner__location", "community__location")
WORLDWIDE = ("owner__match_global", "community__owner__match_global")


@dataclass
class Side:
    """One matchable listing, seen generically."""

    obj: object
    owner: object  # the person who answers for it
    point: object  # None if there is no place, only maybe a country
    country: str
    want: bool
    skill_id: int | None = None
    title: str = ""
    kind: str = ""

    @property
    def is_thing(self):
        return self.kind in Listing.THING_KINDS


def side_of(listing):
    """The Side for a listing, or None if it can't be matched (no one answers for it,
    it is done or its project over, a skill that isn't available)."""
    if not isinstance(listing, Listing):
        return None
    owner = listing.manager
    if owner is None or not listing.is_current or (listing.is_offer and listing.skill_id and not listing.available):
        return None
    return Side(listing, owner, listing.point, listing.country, want=listing.is_wish,
                skill_id=listing.skill_id, title=listing.display_title if not listing.skill_id else "", kind=listing.kind)


def reaches(recipient, other, km):
    """Whether `recipient` side's owner hears about `other`: anywhere if they search
    worldwide or have neither place nor country, in their country if they have only that,
    else within their distance (unknown if `other` has no place)."""
    owner = recipient.owner
    if owner.match_global:
        return True
    if recipient.point is not None:
        return km is not None and km <= (owner.match_radius or 0)
    if recipient.country:
        return other.country == recipient.country
    return True


def candidates(side):
    """The listings on the other side that could fit `side`: nearby (roughly), without a
    place (they may look anywhere or in a country), or anywhere if one of the owners
    searches worldwide. reaches() then decides for each side."""
    others = Listing.objects.current().filter(type=Listing.TYPE_OFFER if side.want else Listing.TYPE_WISH)
    if side.skill_id:
        others = others.filter(skill_id=side.skill_id)
    elif side.is_thing:
        others = others.filter(skill=None, kind__in=Listing.THING_KINDS)
    else:
        others = others.filter(skill=None, kind=side.kind)
    if side.point is not None and not side.owner.match_global:
        near = Q(location=None, owner__location=None, community__location=None)
        for name in PLACES:
            near |= Q(**{f"{name}__dwithin": (side.point, D(km=MAX_RADIUS_KM))})
        for path in WORLDWIDE:
            near |= Q(**{path: True})
        others = others.filter(near)
    return others.select_related("owner", "community__owner", "project__community", "skill").prefetch_related(
        "contributions__match",
    )


def _words(text):
    # Short words ("old", "two", "for") say nothing about what a thing is
    return {word for word in text.casefold().replace(",", " ").split() if len(word) >= 4}


def _same_word(a, b):
    """"scythe" and "scythes", "brick" and "bricks": one starts with the other."""
    return a.startswith(b) or b.startswith(a)


def fit(a, b):
    """Why a and b fit, as a Suggestion reason, or None."""
    if a.want == b.want or bool(a.skill_id) != bool(b.skill_id):
        return None
    if a.skill_id:
        return Suggestion.REASON_SKILL if a.skill_id == b.skill_id else None
    if a.is_thing != b.is_thing:
        return None
    if a.is_thing:
        # "Other" fits any thing; a material doesn't fit a tool
        if Listing.KIND_OTHER not in (a.kind, b.kind) and a.kind != b.kind:
            return None
    elif a.kind != b.kind:
        return None
    if any(_same_word(x, y) for x in _words(a.title) for y in _words(b.title)):
        return Suggestion.REASON_WORDS
    return None


def distance_km(p, q):
    """Great-circle distance between two lon/lat points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (p.x, p.y, q.x, q.y))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _suggest(recipient_side, other_side, reason, km):
    """Create the suggestion for recipient_side's owner, if new and where they look.
    Returns it if it was created."""
    recipient = recipient_side.owner
    if not reaches(recipient_side, other_side, km):
        return None
    suggestion, created = Suggestion.objects.get_or_create(
        user=recipient,
        own_type=ContentType.objects.get_for_model(recipient_side.obj), own_id=str(recipient_side.obj.pk),
        other_type=ContentType.objects.get_for_model(other_side.obj), other_id=str(other_side.obj.pk),
        defaults={
            "other_user": other_side.owner, "reason": reason, "distance_km": None if km is None else round(km),
            "kind": Suggestion.KIND_GIFT if recipient_side.is_thing else Suggestion.KIND_SKILLS,
        },
    )
    return suggestion if created else None


def match(obj, notify=True):
    """Find what fits `obj` and suggest each pair to both sides. Returns the new
    suggestions; with notify, their recipients get a notification right away."""
    side = side_of(obj)
    if side is None:
        return []
    created = []
    for other in candidates(side):
        other_side = side_of(other)
        if other_side is None or other_side.owner == side.owner:
            continue
        reason = fit(side, other_side)
        if reason is None:
            continue
        km = distance_km(side.point, other_side.point) if side.point and other_side.point else None
        for recipient_side, shown in ((side, other_side), (other_side, side)):
            suggestion = _suggest(recipient_side, shown, reason, km)
            if suggestion:
                created.append(suggestion)
    if notify:
        from .emails import notify_new_suggestions
        notify_new_suggestions({s.user for s in created})
    return created


def forget(obj):
    """Remove the suggestions of or for something that was deleted."""
    content_type = ContentType.objects.get_for_model(obj)
    Suggestion.objects.filter(
        Q(own_type=content_type, own_id=str(obj.pk)) | Q(other_type=content_type, other_id=str(obj.pk))
    ).delete()


def match_everything(notify=False):
    """Match all existing things, e.g. after deploying the matching. Returns how many
    suggestions were created."""
    count = 0
    for listing in Listing.objects.current().iterator():
        count += len(match(listing, notify=notify))
    return count

