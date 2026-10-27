"""The matching: when a gift offer or wish, a skill, a skill wish or a project need is
saved, find what fits it nearby and suggest the pair to both sides.

What fits:
- a skill wish (of a person or a community) or a project need for a skill
  ↔ the same skill offered by a person (available) or a community;
- a gift wish or a material/tool need of a project ↔ a gift offer with a similar title
  ("Clay" ~ "Clay from our pond", "Scythe" ~ "Two old scythes"). Not by gift category
  alone: firewood and a chimney pipe are both building materials, but neither helps
  with the other.

Where each side looks, by their owner's settings (reaches()):
- with a place: within their distance (User.match_radius);
- with only a country: in that country;
- with neither: anywhere, as with "search worldwide" (User.match_global).
Nothing is suggested between things of the same person."""

import math
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.measure import D
from django.db.models import Q
from django.utils import timezone

from gifts.models import Listing
from projects.models import Need
from skills.models import CommunitySkill, SkillWish, UserSkill

from .models import Suggestion

# Upper bound for anyone's distance; candidates with a place are looked up within it, then
# each side's own settings decide
MAX_RADIUS_KM = 2000


@dataclass
class Side:
    """One matchable thing, seen generically."""

    obj: object
    owner: object
    point: object  # None if there is no place, only maybe a country
    country: str
    want: bool
    skill_id: int | None = None
    title: str = ""

    @property
    def is_skill(self):
        return self.skill_id is not None


def side_of(obj):
    """The Side for a listing, need, user/community skill or skill wish, or None if it
    can't be matched (no owner, a covered need, a need without a skill …)."""
    side = None
    if isinstance(obj, Listing):
        owner = obj.owner
        if owner is not None:
            side = Side(obj, owner, obj.location or owner.location, str(owner.country or ""),
                        want=obj.type == "wish", title=obj.title)
    elif isinstance(obj, Need):
        project = obj.project
        if not project.is_current or obj.is_done:
            return None
        community = project.community
        place = (community.location, str(community.country or ""))
        if obj.kind in Need.THING_KINDS:
            side = Side(obj, community.owner, *place, want=True, title=obj.title)
        elif obj.skill_id:
            side = Side(obj, community.owner, *place, want=True, skill_id=obj.skill_id)
    elif isinstance(obj, UserSkill):
        if obj.available:
            side = Side(obj, obj.user, obj.user.location, str(obj.user.country or ""), want=False, skill_id=obj.skill_id)
    elif isinstance(obj, CommunitySkill):
        community = obj.community
        side = Side(obj, community.owner, community.location, str(community.country or ""), want=False, skill_id=obj.skill_id)
    elif isinstance(obj, SkillWish):
        if obj.community_id:
            community = obj.community
            side = Side(obj, community.owner, community.location, str(community.country or ""), want=True, skill_id=obj.skill_id)
        elif obj.user_id:
            side = Side(obj, obj.user, obj.user.location, str(obj.user.country or ""), want=True, skill_id=obj.skill_id)
    if side is None or side.owner is None:
        return None
    return side


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


def _near(point, *fields, worldwide=()):
    """Q for any of the location fields within MAX_RADIUS_KM of point, or an owner who
    searches worldwide (the paths to their match_global in `worldwide`)."""
    query = Q()
    for name in fields:
        query |= Q(**{f"{name}__dwithin": (point, D(km=MAX_RADIUS_KM))})
    for path in worldwide:
        query |= Q(**{path: True})
    return query


def _current_needs():
    today = timezone.localdate()
    return Need.objects.filter(
        project__archived_at=None, covered_at=None,
    ).filter(Q(project__ends_on=None) | Q(project__ends_on__gte=today)).select_related(
        "project__community__owner", "skill",
    ).prefetch_related("need_offers__match")


def candidates(side):
    """The things on the other side that could fit `side`: nearby (roughly), without a
    place (they may look anywhere or in a country), or anywhere if one of the owners
    searches worldwide. reaches() then decides for each side."""
    def near(*fields, worldwide=()):
        if side.point is None or side.owner.match_global:
            return Q()
        placeless = Q(**{f"{name}": None for name in fields})
        return _near(side.point, *fields, worldwide=worldwide) | placeless

    if side.is_skill:
        if side.want:
            yield from UserSkill.objects.filter(skill_id=side.skill_id, available=True).filter(
                near("user__location", worldwide=["user__match_global"])).select_related("user")
            yield from CommunitySkill.objects.filter(skill_id=side.skill_id).filter(
                near("community__location", worldwide=["community__owner__match_global"])).select_related("community__owner")
        else:
            yield from SkillWish.objects.filter(skill_id=side.skill_id).filter(
                near("user__location", "community__location",
                      worldwide=["user__match_global", "community__owner__match_global"])).select_related("user", "community__owner")
            yield from _current_needs().filter(skill_id=side.skill_id, kind__in=(Need.KIND_SKILL, Need.KIND_KNOWLEDGE)).filter(
                near("project__community__location", worldwide=["project__community__owner__match_global"]))
        return
    listing_near = near("location", "owner__location", worldwide=["owner__match_global"])
    if side.want:
        yield from Listing.objects.filter(type="offer").filter(listing_near).select_related("owner")
    else:
        yield from Listing.objects.filter(type="wish").filter(listing_near).select_related("owner")
        yield from _current_needs().filter(kind__in=Need.THING_KINDS).filter(
            near("project__community__location", worldwide=["project__community__owner__match_global"]))


def _words(text):
    # Short words ("old", "two", "for") say nothing about what a thing is
    return {word for word in text.casefold().replace(",", " ").split() if len(word) >= 4}


def _same_word(a, b):
    """"scythe" and "scythes", "brick" and "bricks": one starts with the other."""
    return a.startswith(b) or b.startswith(a)


def fit(a, b):
    """Why a and b fit, as a Suggestion reason, or None."""
    if a.want == b.want or a.is_skill != b.is_skill:
        return None
    if a.is_skill:
        return Suggestion.REASON_SKILL if a.skill_id == b.skill_id else None
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
            "kind": Suggestion.KIND_SKILLS if recipient_side.is_skill else Suggestion.KIND_GIFT,
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
    for model in (Listing, UserSkill, CommunitySkill, SkillWish, Need):
        for obj in model.objects.all().iterator():
            count += len(match(obj, notify=notify))
    return count

