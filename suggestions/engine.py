"""The matching: when a gift offer or wish, a skill, a skill wish or a project need is
saved, find what fits it nearby and suggest the pair to both sides.

What fits:
- a skill wish (of a person or a community) or a project need for a skill
  ↔ the same skill offered by a person (available) or a community;
- a gift wish or a material/tool need of a project ↔ a gift offer with a similar title
  ("Clay" ~ "Clay from our pond", "Scythe" ~ "Two old scythes"). Not by gift category
  alone: firewood and a chimney pipe are both building materials, but neither helps
  with the other.

Both sides need a place, and each side only gets suggestions within their own distance
(User.match_radius). Nothing is suggested between things of the same person."""

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

# Upper bound for anyone's distance; candidates are looked up within it, then each side's
# own distance decides
MAX_RADIUS_KM = 2000


@dataclass
class Side:
    """One matchable thing, seen generically."""

    obj: object
    owner: object
    point: object
    want: bool
    skill_id: int | None = None
    title: str = ""

    @property
    def is_skill(self):
        return self.skill_id is not None


def side_of(obj):
    """The Side for a listing, need, user/community skill or skill wish, or None if it
    can't be matched (no owner, no place, a covered need, a need without a skill …)."""
    side = None
    if isinstance(obj, Listing):
        owner = obj.owner
        point = obj.location or (owner.location if owner else None)
        side = Side(obj, owner, point, want=obj.type == "wish", title=obj.title)
    elif isinstance(obj, Need):
        project = obj.project
        if not project.is_current or obj.is_done:
            return None
        community = project.community
        if obj.kind in Need.THING_KINDS:
            side = Side(obj, community.owner, community.location, want=True, title=obj.title)
        elif obj.skill_id:
            side = Side(obj, community.owner, community.location, want=True, skill_id=obj.skill_id)
    elif isinstance(obj, UserSkill):
        if obj.available:
            side = Side(obj, obj.user, obj.user.location, want=False, skill_id=obj.skill_id)
    elif isinstance(obj, CommunitySkill):
        side = Side(obj, obj.community.owner, obj.community.location, want=False, skill_id=obj.skill_id)
    elif isinstance(obj, SkillWish):
        if obj.community_id:
            side = Side(obj, obj.community.owner, obj.community.location, want=True, skill_id=obj.skill_id)
        elif obj.user_id:
            side = Side(obj, obj.user, obj.user.location, want=True, skill_id=obj.skill_id)
    if side is None or side.owner is None or side.point is None:
        return None
    return side


def _near(point, *fields):
    """Q for any of the location fields within MAX_RADIUS_KM of point."""
    query = Q()
    for name in fields:
        query |= Q(**{f"{name}__dwithin": (point, D(km=MAX_RADIUS_KM))})
    return query


def _current_needs():
    today = timezone.localdate()
    return Need.objects.filter(
        project__archived_at=None, covered_at=None,
    ).filter(Q(project__ends_on=None) | Q(project__ends_on__gte=today)).select_related(
        "project__community__owner", "skill",
    ).prefetch_related("need_offers__match")


def candidates(side):
    """The things on the other side that could fit `side`, nearby (roughly)."""
    point = side.point
    if side.is_skill:
        if side.want:
            yield from UserSkill.objects.filter(skill_id=side.skill_id, available=True).filter(
                _near(point, "user__location")).select_related("user")
            yield from CommunitySkill.objects.filter(skill_id=side.skill_id).filter(
                _near(point, "community__location")).select_related("community__owner")
        else:
            yield from SkillWish.objects.filter(skill_id=side.skill_id).filter(
                _near(point, "user__location", "community__location")).select_related("user", "community__owner")
            yield from _current_needs().filter(skill_id=side.skill_id, kind__in=(Need.KIND_SKILL, Need.KIND_KNOWLEDGE)).filter(
                _near(point, "project__community__location"))
        return
    listing_near = _near(point, "location") | (Q(location=None) & _near(point, "owner__location"))
    if side.want:
        yield from Listing.objects.filter(type="offer").filter(listing_near).select_related("owner")
    else:
        yield from Listing.objects.filter(type="wish").filter(listing_near).select_related("owner")
        yield from _current_needs().filter(kind__in=Need.THING_KINDS).filter(_near(point, "project__community__location"))


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
    """Create the suggestion for recipient_side's owner, if new and within their distance.
    Returns it if it was created."""
    recipient = recipient_side.owner
    if km > (recipient.match_radius or 0):
        return None
    suggestion, created = Suggestion.objects.get_or_create(
        user=recipient,
        own_type=ContentType.objects.get_for_model(recipient_side.obj), own_id=str(recipient_side.obj.pk),
        other_type=ContentType.objects.get_for_model(other_side.obj), other_id=str(other_side.obj.pk),
        defaults={"other_user": other_side.owner, "reason": reason, "distance_km": round(km)},
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
        km = distance_km(side.point, other_side.point)
        for recipient_side, shown in ((side, other_side), (other_side, side)):
            suggestion = _suggest(recipient_side, shown, reason, km)
            if suggestion:
                created.append(suggestion)
    if notify:
        from .notifications import notify_new_suggestions
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

